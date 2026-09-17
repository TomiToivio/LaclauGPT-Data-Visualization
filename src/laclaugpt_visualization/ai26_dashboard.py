"""AI26 distributed researcher dashboard.

This is a thin composition layer over the canonical Visualization contracts. MongoDB remains
the durable source of research records/results, Redis is coordination only, and all views are
bounded. The module intentionally does not render or download multimodal blobs.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping
from uuid import uuid4

import pandas as pd
import plotly.express as px
import streamlit as st

from .config import Settings, get_settings
from .data import filter_frame, normalize_frame
from .distributed import ProjectNamespace
from .integrations.hermes import clear_derived_cache, inspect_effective_config
from .provenance import provenance_frame, safe_provenance_events
from .research_views import load_reports, timeline_counts
from .transforms import explore, graph_projection, monitor, relations
from .worker_status import RedisOperationalStatus

AI26_PROJECT_ID = "ai26"
DEFAULT_PAGE_SIZE = 500
MAX_PAGE_SIZE = 5000
MUTABLE_VISUALIZATION_SETTINGS = frozenset(
    {
        "refresh_seconds",
        "default_time_range_days",
        "graph_max_nodes",
        "graph_max_edges",
        "vector_max_results",
        "enabled_plugins",
    }
)

CAVEAT = (
    "Visualization is descriptive. Frequency, centrality, clustering, semantic proximity and "
    "layout position do not by themselves establish hegemony, nodal status, equivalence, "
    "ideological formation or antagonistic frontier. Inspect evidence, uncertainty and review state."
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _decode(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def ai26_namespace(settings: Settings) -> ProjectNamespace:
    """Return the canonical AI26 project namespace, rejecting accidental cross-project use."""
    if settings.project_id != AI26_PROJECT_ID:
        raise ValueError("AI26 dashboard requires LACLAUGPT_VIS_PROJECT_ID=ai26")
    return settings.distributed_namespace


def ai26_collection_names(settings: Settings) -> dict[str, str]:
    ns = ai26_namespace(settings)
    return {
        "records": ns.mongo_collection("records"),
        "processing": ns.mongo_collection("processing"),
        "analyzed": ns.mongo_collection("analyzed"),
        "relations": ns.mongo_collection("relations"),
        "reviews": ns.mongo_collection("reviews"),
        "runs": ns.mongo_collection("runs"),
    }


def ai26_redis_contract(settings: Settings) -> dict[str, str]:
    ns = ai26_namespace(settings)
    return {
        "visualization_settings": ns.settings_key("visualization", "current"),
        "config_events": ns.stream_key("config-events"),
        "rag_messages": ns.stream_key("messages:rag"),
    }


def _mongo_client(settings: Settings):
    try:
        from pymongo import MongoClient
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install laclaugpt-data-visualization[remote] for MongoDB") from exc
    return MongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=settings.mongodb_connect_timeout_ms,
        connectTimeoutMS=settings.mongodb_connect_timeout_ms,
        appname="laclaugpt-ai26-dashboard",
    )


def _redis_client(settings: Settings):
    try:
        import redis
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install laclaugpt-data-visualization[remote] for Redis") from exc
    return redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=1.5,
        socket_timeout=2.0,
        decode_responses=False,
    )


def _first(record: Mapping[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return None


def _identity(record: Mapping[str, Any]) -> str:
    return str(
        _first(
            record,
            (
                "source_url",
                "source_record_id",
                "record_id",
                "canonical_id",
                "_id",
            ),
        )
        or ""
    )


def _merge_record(base: Mapping[str, Any], analysis: Mapping[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if analysis:
        for key, value in analysis.items():
            if key == "_id":
                continue
            if key in {"source", "record", "collected_record"} and isinstance(value, Mapping):
                for nested_key, nested_value in value.items():
                    merged.setdefault(nested_key, nested_value)
                continue
            merged[key] = value
    merged.setdefault("source_url", _identity(base) or _identity(analysis or {}))
    return merged


@dataclass(frozen=True, slots=True)
class LiveSnapshot:
    frame: pd.DataFrame
    counts: Mapping[str, int]
    failures: tuple[Mapping[str, Any], ...]
    loaded_at: str
    query_ms: int
    page_size: int


def load_ai26_snapshot(settings: Settings, *, limit: int = DEFAULT_PAGE_SIZE) -> LiveSnapshot:
    """Load a bounded durable AI26 snapshot from the current records/analyzed contract.

    The Analysis repository currently publishes Collection handoff records in ``records`` and
    durable analysis results in ``analyzed``; failures/in-flight task state lives in ``processing``.
    Results are joined by stable source/record identity without flattening list-valued formations.
    """
    if not settings.mongodb_uri:
        raise RuntimeError("AI26 dashboard requires a private MongoDB URI")
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    names = ai26_collection_names(settings)
    started = time.perf_counter()
    client = _mongo_client(settings)
    try:
        db = client[settings.mongodb_database]
        query = {"project_id": AI26_PROJECT_ID}
        records = list(db[names["records"]].find(query).sort("_id", -1).limit(limit))
        analyses = list(db[names["analyzed"]].find(query).sort("_id", -1).limit(limit))
        processing = list(db[names["processing"]].find(query).sort("_id", -1).limit(limit))
        counts = {
            "records": db[names["records"]].count_documents(query),
            "analyzed": db[names["analyzed"]].count_documents(query),
            "processing": db[names["processing"]].count_documents(query),
        }
    finally:
        client.close()

    analysis_by_id = {_identity(item): item for item in analyses if _identity(item)}
    merged = [_merge_record(item, analysis_by_id.get(_identity(item))) for item in records]
    known = {_identity(item) for item in records if _identity(item)}
    merged.extend(_merge_record({}, item) for item in analyses if _identity(item) not in known)
    frame = normalize_frame(pd.DataFrame(merged))
    failures = tuple(
        item
        for item in processing
        if str(_first(item, ("status", "state", "task_status")) or "").lower()
        in {"failed", "error", "dead_letter", "dead-letter"}
    )
    return LiveSnapshot(
        frame=frame,
        counts=counts,
        failures=failures,
        loaded_at=_now(),
        query_ms=int((time.perf_counter() - started) * 1000),
        page_size=limit,
    )


@dataclass(slots=True)
class RedisAI26ControlPlane:
    """Small adapter for current LaclauGPT Redis Streams/settings contracts."""

    client: Any
    settings: Settings

    @property
    def keys(self) -> Mapping[str, str]:
        return ai26_redis_contract(self.settings)

    def effective_visualization_config(self) -> dict[str, Any]:
        raw = self.client.get(self.keys["visualization_settings"])
        if raw is None:
            return {"revision": None, "values": {}}
        payload = json.loads(_decode(raw))
        if not isinstance(payload, dict):
            raise TypeError("visualization settings pointer must be a JSON object")
        values = payload.get("values", payload.get("config", payload))
        if not isinstance(values, dict):
            values = {}
        return {
            "revision": payload.get("revision") or payload.get("version"),
            "values": {key: value for key, value in values.items() if "secret" not in key.lower()},
        }

    def publish_visualization_config(
        self,
        changes: Mapping[str, Any],
        *,
        actor: str,
        reason: str,
    ) -> str:
        unknown = set(changes) - MUTABLE_VISUALIZATION_SETTINGS
        if unknown:
            raise ValueError("settings are read-only or unsupported: " + ", ".join(sorted(unknown)))
        if not reason.strip():
            raise ValueError("a reason is required")
        request_id = str(uuid4())
        envelope = {
            "project_id": AI26_PROJECT_ID,
            "request_id": request_id,
            "correlation_id": request_id,
            "sender": "visualization-ui",
            "recipient": "visualization",
            "message_type": "config.publish",
            "created_at": _now(),
            "body": json.dumps(
                {"changes": dict(changes), "actor": actor, "reason": reason},
                ensure_ascii=False,
                sort_keys=True,
            ),
        }
        self.client.xadd(self.keys["config_events"], envelope, maxlen=10000, approximate=True)
        return request_id

    def rag_request(
        self,
        question: str,
        *,
        actor: str,
        filters: Mapping[str, Any] | None = None,
    ) -> str:
        if not question.strip():
            raise ValueError("question must not be empty")
        request_id = str(uuid4())
        body = {
            "question": question.strip(),
            "filters": dict(filters or {}),
            "actor": actor,
        }
        envelope = {
            "project_id": AI26_PROJECT_ID,
            "request_id": request_id,
            "correlation_id": request_id,
            "sender": "visualization-ui",
            "recipient": "rag",
            "message_type": "rag.query",
            "created_at": _now(),
            "body": json.dumps(body, ensure_ascii=False, sort_keys=True),
        }
        self.client.xadd(self.keys["rag_messages"], envelope, maxlen=10000, approximate=True)
        return request_id

    def rag_response(self, correlation_id: str, *, scan: int = 100) -> dict[str, Any] | None:
        """Read a recent matching response without consuming/deleting the shared stream."""
        rows = self.client.xrevrange(self.keys["rag_messages"], count=max(1, min(scan, 500)))
        for message_id, raw in rows:
            item = {_decode(key): _decode(value) for key, value in raw.items()}
            if item.get("correlation_id") != correlation_id:
                continue
            if item.get("message_type") not in {"rag.response", "rag.answer", "response"}:
                continue
            body = item.get("body", "{}")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"answer": body}
            parsed["stream_message_id"] = _decode(message_id)
            return parsed
        return None


def _list_values(frame: pd.DataFrame, column: str) -> list[str]:
    if column not in frame:
        return []
    values: set[str] = set()
    for value in frame[column]:
        if isinstance(value, (list, tuple, set)):
            values.update(str(item) for item in value if item not in (None, ""))
        elif value not in (None, ""):
            values.add(str(value))
    return sorted(values)


def apply_ai26_filters(frame: pd.DataFrame, selections: Mapping[str, Iterable[str]], query: str = "") -> pd.DataFrame:
    """Apply shared researcher filters while preserving list-valued formation semantics."""
    return filter_frame(
        frame,
        query=query,
        platforms=list(selections.get("platforms", ())),
        countries=list(selections.get("countries", ())),
        languages=list(selections.get("languages", ())),
        formations=list(selections.get("formations", ())),
    )


def _sidebar(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    st.sidebar.markdown("### AI26 filters")
    query = st.sidebar.text_input("Search text")
    platform_col = "source_platform" if "source_platform" in frame else "source_type"
    language_col = "source_language" if "source_language" in frame else "language"
    country_col = "source_country" if "source_country" in frame else "country"
    platforms = st.sidebar.multiselect("Source/platform", _list_values(frame, platform_col))
    languages = st.sidebar.multiselect("Language", _list_values(frame, language_col))
    countries = st.sidebar.multiselect("Country/region", _list_values(frame, country_col))
    formations = st.sidebar.multiselect("Formation", _list_values(frame, "formations"))
    selections = {
        "platforms": platforms,
        "languages": languages,
        "countries": countries,
        "formations": formations,
    }
    filtered = apply_ai26_filters(frame, selections, query=query)
    st.sidebar.caption(f"Active view: {len(filtered):,} / {len(frame):,} loaded records")
    return filtered, selections


def _monitor(snapshot: LiveSnapshot, frame: pd.DataFrame) -> None:
    values = monitor(frame)
    cols = st.columns(6)
    cols[0].metric("Collected", f"{snapshot.counts['records']:,}")
    cols[1].metric("Analyzed", f"{snapshot.counts['analyzed']:,}")
    cols[2].metric("Processing", f"{snapshot.counts['processing']:,}")
    cols[3].metric("Loaded", f"{len(frame):,}")
    cols[4].metric("Query", f"{snapshot.query_ms} ms")
    cols[5].metric("Failures in page", len(snapshot.failures))
    timeline = timeline_counts(frame)
    if not timeline.empty:
        st.plotly_chart(px.line(timeline, x="period", y="documents", color="time_kind", markers=True), use_container_width=True)
    for key, title in (("formations", "Formations"), ("signifiers", "Signifiers"), ("actors", "Actors")):
        table = values[key]
        if not table.empty:
            st.plotly_chart(px.bar(table.head(20), x="count", y=table.columns[0], orientation="h", title=title), use_container_width=True)
    st.caption(CAVEAT)


def _explore(frame: pd.DataFrame) -> None:
    views = explore(frame)
    columns = st.columns(3)
    for target, column in zip(("formations", "topics", "entities"), columns, strict=True):
        table = views[target].head(40)
        column.markdown(f"#### {target.title()}")
        column.dataframe(table, use_container_width=True, hide_index=True)
    if "signifiers" in frame:
        rows = []
        for formation_list, signifier_list in zip(frame.get("formations", []), frame.get("signifiers", [])):
            for formation in formation_list or []:
                for signifier in signifier_list or []:
                    rows.append({"formation": str(formation), "signifier": str(signifier)})
        if rows:
            cross = pd.DataFrame(rows).value_counts(["formation", "signifier"]).reset_index(name="count")
            st.markdown("#### Formation × signifier")
            st.dataframe(cross.head(100), use_container_width=True, hide_index=True)
    st.caption(CAVEAT)


def _networks(frame: pd.DataFrame) -> None:
    projection = graph_projection(frame)
    st.metric("Nodes", len(projection["nodes"]))
    st.metric("Edges", len(projection["edges"]))
    if projection["nodes"]:
        st.dataframe(pd.DataFrame(projection["nodes"]).head(500), use_container_width=True, hide_index=True)
    if projection["edges"]:
        st.dataframe(pd.DataFrame(projection["edges"]).head(1000), use_container_width=True, hide_index=True)
    rel = relations(frame)
    if not rel.empty:
        st.markdown("#### Evidence-bearing relations")
        st.dataframe(rel.head(1000), use_container_width=True, hide_index=True)
    st.caption(CAVEAT)


def _records(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.info("No records match the current filters.")
        return
    cols = [column for column in ("source_url", "source_platform", "source_author", "source_language", "analysis_status", "summary") if column in frame]
    st.dataframe(frame[cols] if cols else frame, use_container_width=True, hide_index=True)
    source_urls = [value for value in frame.get("source_url", []) if str(value)]
    if not source_urls:
        return
    selected = st.selectbox("Close-read record", source_urls)
    row = frame[frame["source_url"] == selected].iloc[0]
    st.markdown("#### Text / metadata")
    st.write(row.get("summary") or row.get("human_readable_summary") or "No summary")
    for field in ("text", "caption", "transcript", "whisper_transcript", "ocr"):
        if row.get(field):
            st.markdown(f"**{field}**")
            st.write(row.get(field))
    st.markdown("#### Analysis")
    st.json({key: row.get(key) for key in ("formations", "signifiers", "topics", "entities", "discourses", "us", "them", "frontier", "uncertainties", "abstentions", "evidence") if key in row})
    with st.expander("Safe provenance"):
        st.json(safe_provenance_events(row))
        projected = provenance_frame(pd.DataFrame([row])).to_dict(orient="records")
        if projected:
            st.json(projected[0])


def _reports(settings: Settings, frame: pd.DataFrame) -> None:
    reports = load_reports(settings.data_path("reports"))
    if not reports:
        st.info("No locally materialized periodic reports are available yet.")
        return
    labels = [f"{item.date.date().isoformat() if item.date else 'undated'} · {item.title}" for item in reports]
    report = reports[labels.index(st.selectbox("Periodic report", labels))]
    st.markdown(report.body)
    if report.source_urls:
        linked = frame[frame["source_url"].isin(report.source_urls)]
        st.caption(f"Evidence links visible in current filtered view: {len(linked)}")


def _rag(settings: Settings, filters: Mapping[str, Any]) -> None:
    st.caption("RAG is an upstream service. This panel sends bounded Redis Stream requests and renders only returned evidence references.")
    if settings.messaging_backend != "redis" or not settings.redis_url:
        st.info("RAG messaging is disabled in this deployment.")
        return
    client = _redis_client(settings)
    control = RedisAI26ControlPlane(client, settings)
    history = st.session_state.setdefault("ai26_rag_history", [])
    for item in history[-20:]:
        with st.chat_message(item["role"]):
            st.write(item["content"])
            if item.get("evidence"):
                st.json(item["evidence"])
    question = st.chat_input("Ask about analyzed AI26 data")
    if question:
        correlation_id = control.rag_request(question, actor="dashboard-researcher", filters=filters)
        history.append({"role": "user", "content": question, "correlation_id": correlation_id})
        st.session_state["ai26_rag_pending"] = correlation_id
        st.rerun()
    pending = st.session_state.get("ai26_rag_pending")
    if pending:
        response = control.rag_response(pending)
        if response:
            history.append({"role": "assistant", "content": response.get("answer") or response.get("text") or "RAG returned a response without answer text.", "evidence": response.get("evidence") or response.get("sources") or response.get("references") or []})
            st.session_state.pop("ai26_rag_pending", None)
            st.rerun()
        st.info(f"Waiting for RAG response · correlation_id={pending}")


def _configuration(settings: Settings) -> None:
    st.caption("Only explicitly safe Visualization settings can be proposed here. Secrets and upstream Analysis/Collection settings remain read-only.")
    st.json(inspect_effective_config(settings))
    if settings.messaging_backend != "redis" or not settings.redis_url:
        st.info("Redis control plane is disabled; effective configuration is read-only.")
        return
    client = _redis_client(settings)
    control = RedisAI26ControlPlane(client, settings)
    current = control.effective_visualization_config()
    st.markdown("#### Distributed Visualization configuration")
    st.json(current)
    field = st.selectbox("Mutable setting", sorted(MUTABLE_VISUALIZATION_SETTINGS))
    value = st.text_input("Proposed JSON value", value="null")
    reason = st.text_input("Reason for change")
    confirmed = st.checkbox("I confirm publishing this project-scoped configuration proposal")
    if st.button("Publish configuration proposal", disabled=not confirmed):
        parsed = json.loads(value)
        request_id = control.publish_visualization_config({field: parsed}, actor="dashboard-researcher", reason=reason)
        st.success(f"Published config event {request_id}. The receiving module must validate/apply it.")


def _hermes(settings: Settings, frame: pd.DataFrame) -> None:
    st.caption("Hermes is bounded to Visualization-owned diagnostics, summaries, review requests and explicit coordination actions. No shell access is exposed here.")
    st.json(inspect_effective_config(settings))
    st.json({"records_in_filtered_view": len(frame), "columns": sorted(frame.columns)[:100]})
    if st.button("Clear local derived cache"):
        st.json(clear_derived_cache(settings))


def _diagnostics(settings: Settings, snapshot: LiveSnapshot, frame: pd.DataFrame) -> None:
    st.json(
        {
            "project_id": settings.project_id,
            "loaded_at": snapshot.loaded_at,
            "query_ms": snapshot.query_ms,
            "page_size": snapshot.page_size,
            "loaded_records": len(frame),
            "mongo_collections": ai26_collection_names(settings),
            "redis_contract": ai26_redis_contract(settings),
            "safe_config": settings.safe_summary(),
        }
    )
    if settings.messaging_backend == "redis" and settings.redis_url:
        try:
            import redis
            client = _redis_client(settings)
            status = RedisOperationalStatus(
                client,
                prefix=settings.redis_key_prefix,
                heartbeat_ttl_seconds=settings.redis_heartbeat_ttl_seconds,
                event_limit=settings.redis_event_limit,
                error_types=(redis.exceptions.RedisError, ConnectionError, OSError, TimeoutError, TypeError, ValueError),
            ).snapshot(settings.project_id)
            st.json({"redis_available": status.available, "workers": len(status.workers), "events": len(status.events), "note": status.note})
        except Exception as exc:  # diagnostics must not take down durable dashboard
            st.warning(f"Redis diagnostics unavailable: {type(exc).__name__}")
    st.caption("This dashboard assumes host/network-level access control. Do not expose it to the public Internet without authentication or reverse-proxy access control.")


def run() -> None:
    st.set_page_config(page_title="LaclauGPT AI26 Research Dashboard", layout="wide")
    st.title("LaclauGPT · AI26 Research Dashboard")
    st.caption("Live distributed research instrument · MongoDB durable state · Redis coordination · no multimodal blob display")
    st.warning(CAVEAT)
    settings = get_settings()
    ai26_namespace(settings)
    if settings.storage != "distributed" or settings.data_backend != "mongodb":
        st.error("AI26 live dashboard requires distributed storage with MongoDB durable data.")
        return
    page_size = st.sidebar.number_input("Loaded live window", min_value=100, max_value=MAX_PAGE_SIZE, value=DEFAULT_PAGE_SIZE, step=100)
    refresh = st.sidebar.number_input("Refresh seconds", min_value=5, max_value=300, value=30, step=5)
    if st.sidebar.button("Refresh now"):
        st.cache_data.clear()
    snapshot = load_ai26_snapshot(settings, limit=int(page_size))
    filtered, filters = _sidebar(snapshot.frame)
    st.sidebar.caption(f"Last load: {snapshot.loaded_at} · auto-refresh target: {refresh}s")
    tabs = st.tabs(["Monitor", "Explore", "Networks", "Records", "Reports", "RAG Chat", "Configuration", "Hermes", "Diagnostics"])
    functions = (
        lambda: _monitor(snapshot, filtered),
        lambda: _explore(filtered),
        lambda: _networks(filtered),
        lambda: _records(filtered),
        lambda: _reports(settings, filtered),
        lambda: _rag(settings, filters),
        lambda: _configuration(settings),
        lambda: _hermes(settings, filtered),
        lambda: _diagnostics(settings, snapshot, filtered),
    )
    for tab, function in zip(tabs, functions, strict=True):
        with tab:
            function()


if __name__ == "__main__":
    run()
