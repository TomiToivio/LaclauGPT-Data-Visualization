"""AI26 distributed researcher dashboard.

MongoDB is the durable source of research state. Redis is coordination only. This module
composes the existing Visualization contracts into a bounded private AI26 research workbench
and never downloads multimodal blobs merely for display.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import plotly.express as px
import streamlit as st

from laclaugpt_visualization.ai26_research_ux import (
    chart_style,
    render_corpus_charts,
    render_distribution,
    render_header,
    render_overlap,
    render_record_picker,
    researcher_table,
)
from laclaugpt_visualization.canonical_explore import canonical_explore
from laclaugpt_visualization.config import Settings, get_settings
from laclaugpt_visualization.data import filter_frame, load_frame, normalize_frame
from laclaugpt_visualization.distributed import ProjectNamespace
from laclaugpt_visualization.integrations.hermes import (
    clear_derived_cache,
    inspect_effective_config,
)
from laclaugpt_visualization.research_views import load_reports, timeline_counts
from laclaugpt_visualization.transforms import monitor
from laclaugpt_visualization.worker_status import RedisOperationalStatus

AI26_PROJECT_ID = "ai26"
DEFAULT_PAGE_SIZE = 500
MAX_PAGE_SIZE = 5000
FRESHNESS_WARNING_HOURS = 6
#: Views a public copy may render (issue #342). Everything else reads a private service, writes
#: review state, or exposes host configuration, so a demo copy does not build those tabs at all.
DEMO_TABS = ("Explore", "Networks", "Records")
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


def _as_utc_timestamp(value: Any) -> datetime | None:
    """Parse legacy epoch, BSON datetime, and ISO timestamps safely."""
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            dt = datetime.fromtimestamp(float(value), tz=UTC)
        elif isinstance(value, str) and value.strip():
            dt = datetime.fromisoformat(value.strip())
        else:
            return None
        return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _readable_text(value: Any, fallback: str = "Not available") -> str:
    """Keep missing pandas values and nested text from breaking close reading."""
    if value is None or value is pd.NA:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    try:
        if bool(pd.isna(value)):
            return fallback
    except (ValueError, TypeError):
        pass
    return str(value)


def _ranked_bar(table: pd.DataFrame, label_column: str, title: str):
    """Horizontal bars ordered so the most frequent item is prominent."""
    subset = table.head(15).copy()
    subset[label_column] = subset[label_column].astype(str)
    subset = subset.iloc[::-1]
    figure = px.bar(
        subset,
        x="count",
        y=label_column,
        orientation="h",
        title=title,
        labels={"count": "Records", label_column: "Label"},
        text="count",
    )
    figure.update_layout(
        height=max(280, min(620, 115 + len(subset) * 30)),
        margin={"l": 12, "r": 20, "t": 48, "b": 28},
        yaxis_title=None,
        showlegend=False,
    )
    figure.update_traces(textposition="outside", cliponaxis=False)
    return figure


def _decode(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def ai26_namespace(settings: Settings) -> ProjectNamespace:
    if settings.project_id != AI26_PROJECT_ID:
        raise ValueError("AI26 dashboard requires LACLAUGPT_VIS_PROJECT_ID=ai26")
    return settings.distributed_namespace


def ai26_collection_names(settings: Settings) -> dict[str, str]:
    ns = ai26_namespace(settings)
    return {
        "records": ns.mongo_collection("records"),
        "processing": ns.mongo_collection("processing"),  # Legacy diagnostics only.
        "analyzed": settings.expected_mongodb_collection,
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
        _first(record, ("source_url", "source_record_id", "record_id", "canonical_id", "_id")) or ""
    )


def _merge_record(base: Mapping[str, Any], analysis: Mapping[str, Any] | None) -> dict[str, Any]:
    """Join source/result views without flattening list-valued scientific fields."""
    merged = dict(base)
    if analysis:
        for key, value in analysis.items():
            if key == "_id":
                continue
            if key in {"source", "record", "collected_record"} and isinstance(value, Mapping):
                for nested_key, nested_value in value.items():
                    merged.setdefault(nested_key, nested_value)
            else:
                merged[key] = value
    merged.setdefault("source_url", _identity(base) or _identity(analysis or {}))
    return merged


@dataclass(frozen=True, slots=True)
class LiveSnapshot:
    frame: pd.DataFrame
    counts: Mapping[str, int]
    failures: tuple[Mapping[str, Any], ...]
    loaded_at: str
    newest_analyzed_at: str | None
    analyzed_age_hours: float | None
    query_ms: int
    page_size: int


def load_ai26_snapshot(settings: Settings, *, limit: int = DEFAULT_PAGE_SIZE) -> LiveSnapshot:
    """Read a bounded project-scoped snapshot using canonical durable analysis results."""
    if not settings.mongodb_uri:
        raise RuntimeError("AI26 dashboard requires a private MongoDB URI")
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    names = ai26_collection_names(settings)
    query = {"project_id": AI26_PROJECT_ID}
    started = time.perf_counter()
    client = _mongo_client(settings)
    try:
        db = client[settings.mongodb_database]
        records = list(db[names["records"]].find(query).sort("_id", -1).limit(limit))
        analyses = list(db[names["analyzed"]].find(query).sort("_id", -1).limit(limit))
        processing = list(db[names["processing"]].find(query).sort("_id", -1).limit(limit))
        counts = {
            "records": db[names["records"]].count_documents(query),
            "analyzed": db[names["analyzed"]].count_documents(query),
            "processing": db[names["processing"]].count_documents(query),
        }
        newest_analyzed = db[names["analyzed"]].find_one(
            {**query, "created_at": {"$exists": True, "$ne": None}},
            sort=[("created_at", -1)],
            projection={"created_at": 1},
        )
    finally:
        client.close()

    analysis_by_id = {_identity(item): item for item in analyses if _identity(item)}
    merged = [_merge_record(item, analysis_by_id.get(_identity(item))) for item in records]
    known = {_identity(item) for item in records if _identity(item)}
    merged.extend(_merge_record({}, item) for item in analyses if _identity(item) not in known)
    failures = tuple(
        item
        for item in processing
        if str(_first(item, ("status", "state", "task_status")) or "").lower()
        in {"failed", "error", "dead_letter", "dead-letter"}
    )
    # MongoDB compares BSON types before values: mixed legacy epoch floats
    # and BSON datetimes cannot be ordered reliably by one created_at sort.
    # Supplement the queried newest row with the bounded analysis window.
    candidates = [newest_analyzed.get("created_at")] if newest_analyzed else []
    candidates.extend(row.get("created_at") for row in analyses)
    valid = [dt for value in candidates if (dt := _as_utc_timestamp(value)) is not None]
    newest = max(valid, default=None)
    newest_analyzed_at = newest.isoformat() if newest else None
    analyzed_age_hours = (
        max(0.0, (datetime.now(UTC) - newest).total_seconds() / 3600)
        if newest is not None
        else None
    )

    return LiveSnapshot(
        frame=normalize_frame(pd.DataFrame(merged)),
        counts=counts,
        failures=failures,
        loaded_at=_now(),
        newest_analyzed_at=newest_analyzed_at,
        analyzed_age_hours=analyzed_age_hours,
        query_ms=int((time.perf_counter() - started) * 1000),
        page_size=limit,
    )


@dataclass(slots=True)
class RedisAI26ControlPlane:
    """Project-scoped Redis Streams/settings adapter using the shared coordination contract."""

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
        redacted = {
            key: value
            for key, value in values.items()
            if not any(token in key.lower() for token in ("secret", "password", "token", "key"))
        }
        return {
            "revision": payload.get("revision") or payload.get("version"),
            "values": redacted,
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
        self.client.xadd(
            self.keys["config_events"],
            {
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
            },
            maxlen=10000,
            approximate=True,
        )
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
        self.client.xadd(
            self.keys["rag_messages"],
            {
                "project_id": AI26_PROJECT_ID,
                "request_id": request_id,
                "correlation_id": request_id,
                "sender": "visualization-ui",
                "recipient": "rag",
                "message_type": "rag.query",
                "created_at": _now(),
                "body": json.dumps(
                    {
                        "question": question.strip(),
                        "filters": dict(filters or {}),
                        "actor": actor,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
            maxlen=10000,
            approximate=True,
        )
        return request_id

    def rag_response(self, correlation_id: str, *, scan: int = 100) -> dict[str, Any] | None:
        for message_id, raw in self.client.xrevrange(
            self.keys["rag_messages"], count=max(1, min(scan, 500))
        ):
            item = {_decode(key): _decode(value) for key, value in raw.items()}
            if item.get("correlation_id") != correlation_id:
                continue
            if item.get("message_type") not in {"rag.response", "rag.answer", "response"}:
                continue
            try:
                parsed = json.loads(item.get("body", "{}"))
            except json.JSONDecodeError:
                parsed = {"answer": item.get("body", "")}
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


def apply_ai26_filters(
    frame: pd.DataFrame,
    selections: Mapping[str, Iterable[str]],
    query: str = "",
) -> pd.DataFrame:
    return filter_frame(
        frame,
        query=query,
        platforms=list(selections.get("platforms", ())),
        countries=list(selections.get("countries", ())),
        languages=list(selections.get("languages", ())),
        formations=list(selections.get("formations", ())),
        authors=list(selections.get("authors", ())),
        topics=list(selections.get("topics", ())),
    )


def _sidebar(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    from laclaugpt_visualization.ai26_networks import (
        coded_labels,
        filter_coded_records,
        filter_publication_window,
        period_bounds,
    )

    st.sidebar.markdown("### AI26 filters")
    query = st.sidebar.text_input("Search text")
    selections = {
        "platforms": st.sidebar.multiselect(
            "Source/platform", _list_values(frame, "source_platform")
        ),
        "languages": st.sidebar.multiselect("Language", _list_values(frame, "source_language")),
        "countries": st.sidebar.multiselect(
            "Country/region", _list_values(frame, "source_country")
        ),
        "formations": st.sidebar.multiselect("Formation", _list_values(frame, "formations")),
        "authors": st.sidebar.multiselect(
            "Username / account", _list_values(frame, "source_author")
        ),
        "topics": st.sidebar.multiselect("Topic / concept", _list_values(frame, "topics")),
    }
    actors = sorted(
        {label for row in frame.to_dict("records") for label in coded_labels(row, "entities")}
    )
    empties = sorted(
        {
            label
            for row in frame.to_dict("records")
            for label in coded_labels(row, "empty_signifier_candidates")
        }
    )
    selections["actors"] = st.sidebar.multiselect("Coded actor", actors)
    selections["empty_signifiers"] = st.sidebar.multiselect("Empty-signifier candidate", empties)
    preset = st.sidebar.selectbox(
        "Publication period (UTC)",
        (
            "All loaded dates",
            "Last 24 hours",
            "Last 7 days",
            "Selected UTC day",
            "Selected UTC week",
            "Custom UTC dates",
        ),
    )
    day = last = None
    if preset in {"Selected UTC day", "Selected UTC week", "Custom UTC dates"}:
        day = st.sidebar.date_input(
            "Any day in week" if preset == "Selected UTC week" else "Start / selected day",
        )
    if preset == "Custom UTC dates":
        last = st.sidebar.date_input("End date (inclusive)")
    filtered = apply_ai26_filters(frame, selections, query=query)
    filtered = filter_coded_records(
        filtered,
        actors=tuple(selections["actors"]),
        empty_signifiers=tuple(selections["empty_signifiers"]),
    )
    try:
        start, end = period_bounds(preset, selected_start=day, selected_end=last)
        filtered = filter_publication_window(filtered, start, end)
        selections["publication_start"] = start.isoformat() if start is not None else None
        selections["publication_end_exclusive"] = end.isoformat() if end is not None else None
    except ValueError as exc:
        st.sidebar.warning(str(exc))
        filtered = filtered.iloc[0:0]
    st.sidebar.caption(
        "Publication clock only. Missing publication dates are excluded from dated views."
    )
    st.sidebar.caption(f"Active view: {len(filtered):,} / {len(frame):,} loaded records")
    return filtered, selections


def _monitor(snapshot: LiveSnapshot, frame: pd.DataFrame) -> None:
    st.markdown("### Corpus overview")
    st.caption(
        "Collected and analyzed totals refer to all project documents in MongoDB. "
        "Charts and filters use only the most recently loaded records; the window "
        f"is capped at {snapshot.page_size:,} per collection and is not a representative sample."
    )
    totals = st.columns(3)
    totals[0].metric(
        "Collected records · corpus",
        snapshot.counts["records"],
        help="Project-wide collected source records in MongoDB.",
    )
    totals[1].metric(
        "Stored analyses · corpus",
        snapshot.counts["analyzed"],
        help="Project-wide durable result documents, including possible reruns of a source.",
    )
    totals[2].metric(
        "Filtered records · loaded window",
        len(frame),
        help="Current view after filters. This is the denominator for the charts below.",
    )
    if snapshot.counts["records"]:
        st.caption(
            f"Storage ratio: {snapshot.counts['analyzed']:,} analysis results / "
            f"{snapshot.counts['records']:,} collected records. "
            "This is not unique-source coverage because a source may have multiple analyses."
        )
    with st.expander("Operational details and data coverage"):
        st.caption(
            f"Loaded up to {snapshot.page_size:,} documents per collection. "
            f"Database query: {snapshot.query_ms} ms. Legacy processing entries: "
            f"{snapshot.counts['processing']:,}; legacy failures in page: "
            f"{len(snapshot.failures):,}. Multiple versions of an analysis can "
            "exist for one source, so stored analyses are not unique sources."
        )
    if snapshot.analyzed_age_hours is None:
        st.warning(
            "Analysis freshness unavailable: no durable analysis result with a valid timestamp was found."
        )
    elif snapshot.analyzed_age_hours >= FRESHNESS_WARNING_HOURS:
        st.warning(
            f"Analysis is stale: newest visible stored analysis is {snapshot.analyzed_age_hours:.1f} hours old "
            f"({snapshot.newest_analyzed_at}). Inspect the worker before concluding the pipeline stopped."
        )
    else:
        st.caption(
            f"Analysis freshness: newest analyzed record is {snapshot.analyzed_age_hours:.1f} "
            f"hours old ({snapshot.newest_analyzed_at})."
        )
    render_corpus_charts(frame)
    values = monitor(frame)
    timeline = timeline_counts(frame)
    if not timeline.empty:
        st.markdown("#### Records across time")
        st.caption("Source, collection, analysis and event clocks describe different timestamps.")
        st.plotly_chart(
            chart_style(
                px.line(
                    timeline,
                    x="period",
                    y="documents",
                    color="time_kind",
                    markers=True,
                    labels={"period": "Date", "documents": "Records", "time_kind": "Clock"},
                )
            ),
            width="stretch",
        )
    # Side by side rather than stacked: formations, signifiers and actors are read as a set, and
    # three full-width charts meant three scrolls to compare them.
    for column, (key, title) in zip(
        st.columns(3),
        (("formations", "Formations"), ("signifiers", "Signifiers"), ("actors", "Actors")),
        strict=True,
    ):
        table = values[key]
        column.markdown(f"#### {title}")
        if not isinstance(table, pd.DataFrame) or table.empty:
            # main's wording (#290): name what is missing from *this window*, not "none".
            column.caption(f"No {title.lower()} in the current filtered window.")
            continue
        column.plotly_chart(
            chart_style(
                px.bar(table.head(12).iloc[::-1], x="count", y=table.columns[0], orientation="h")
            ),
            width="stretch",
            height=340,
        )


def _explore(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.info("No records match the current filters.")
        return

    try:
        with st.spinner("Building canonical Explore views…"):
            views = canonical_explore(frame)
    except (KeyError, TypeError, ValueError) as exc:
        st.error(f"Explore view could not be built: {exc}")
        return

    timeline = views["timeline"]
    st.markdown("#### Timeline")
    if timeline.empty:
        st.info("No canonical timestamps are available in the current view.")
    else:
        st.plotly_chart(
            px.line(
                timeline,
                x="period",
                y="documents",
                color="time_kind",
                markers=True,
                title="Source, collection, analysis and event clocks",
            ),
            width="stretch",
        )

    for target in ("formations", "topics", "entities", "signifiers"):
        st.markdown(f"#### {target.title()}")
        render_distribution(frame, views[target], target, target.title())

    st.markdown("#### Formation × signifier")
    render_overlap(frame, views["formation_signifier"])


def _networks(
    frame: pd.DataFrame,
    settings: Settings | None = None,
    *,
    artifact_path: Path | None = None,
) -> None:
    from streamlit.components.v1 import html

    from laclaugpt_visualization.ai26_graph_render import graph_html
    from laclaugpt_visualization.ai26_networks import (
        LAYERS,
        graph_view,
        load_mongo_artifact,
    )

    st.markdown("### Discourse and social networks")
    st.caption(
        "DA: coded relations · DNA: experimental coded statements · SNA: experimental "
        "social ties. Shared producer IDs connect layers, never similar names. Dashed edges "
        "indicate coded/inferred assertions; layout and visible degree are descriptive."
    )
    artifact = None
    if artifact_path is not None:
        # Issue #342: a copied demo ships a versioned graph bundle and never reaches a database.
        try:
            artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            st.warning(
                f"Bundled graph artifact unreadable ({type(artifact_path).__name__}); "
                "showing explicit DA relations only."
            )
            artifact = None
    if settings is not None and not frame.empty:
        client = None
        try:
            client = _mongo_client(settings)
            artifact = load_mongo_artifact(
                client[settings.mongodb_database],
                set(frame["source_url"].astype(str)),
            )
        except Exception as exc:  # noqa: BLE001 -- optional upstream graph must not disable DA
            st.warning(f"Upstream graph unavailable: {type(exc).__name__}.")
        finally:
            if client is not None:
                client.close()
    uploaded = st.file_uploader(
        "Optional private Analysis AnalyticalGraph JSON export", type=["json"]
    )
    if uploaded is not None:
        try:
            artifact = json.loads(uploaded.getvalue())
            if not isinstance(artifact, Mapping):
                raise TypeError("Expected a JSON object.")
        except (ValueError, TypeError) as exc:
            st.warning(f"Cannot open graph: {type(exc).__name__}.")
            artifact = None
    if artifact is None:
        st.info(
            "No validated upstream graph available. Showing explicit DA relations only; no DNA/SNA inferred."
        )
    try:
        baseline = graph_view(frame, artifact)
    except (ValueError, TypeError) as exc:
        st.warning(f"Upstream graph rejected: {exc}")
        artifact = None
        baseline = graph_view(frame)
    left, right, third = st.columns(3)
    for col, layer in zip((left, right, third), LAYERS, strict=True):
        col.metric(f"{layer.upper()} available edges", baseline["availability"][layer])
    chosen = st.multiselect(
        "Network layers", list(LAYERS), default=list(LAYERS), format_func=str.upper
    )
    types = sorted({edge["type"] for edge in baseline["edges"] if edge.get("type")})
    edge_types = st.multiselect("Relation types (visible preview)", types)
    a, b, c = st.columns(3)
    nodes = a.number_input("Node limit", 10, 500, 250, 10)
    edges = b.number_input("Edge limit", 10, 1000, 500, 10)
    weight = c.number_input("Minimum reported edge weight", min_value=0.0, value=0.0)
    graph = graph_view(
        frame,
        artifact,
        layers=tuple(chosen),
        max_nodes=int(nodes),
        max_edges=int(edges),
        min_weight=float(weight),
        edge_types=tuple(edge_types),
    )
    st.caption(
        f"{len(graph['nodes'])} nodes · {len(graph['edges'])} displayed edges / "
        f"{graph['matched_edges']} matching in the loaded source window."
    )
    if graph["truncated"] or graph["input_truncated"]:
        st.warning("Graph is bounded/truncated; not the full network. Narrow the source filters.")
    if graph["omitted_unlinked_edges"]:
        st.caption(
            f"{graph['omitted_unlinked_edges']} upstream edges lack usable source/endpoint links."
        )
    if not graph["edges"]:
        st.info("No explicit relations match this combination of filters.")
    else:
        html(graph_html(graph), height=730, scrolling=True)
        st.download_button(
            "Download visible graph JSON",
            json.dumps(graph, ensure_ascii=False, default=str),
            "ai26-network.json",
            "application/json",
        )
        with st.expander("Evidence-bearing relations"):
            ids = {node["id"]: node["label"] for node in graph["nodes"]}
            evidence = pd.DataFrame(
                [
                    {
                        "From": ids[edge["source"]],
                        "To": ids[edge["target"]],
                        "Layer": edge["layer"].upper(),
                        "Relation": edge["type"],
                        "Review": edge.get("review_status"),
                        "Stance": edge.get("stance"),
                        "Source": edge["source_url"],
                        "Evidence": ", ".join(
                            map(str, edge["provenance"].get("evidence_ids") or [])
                        ),
                    }
                    for edge in graph["edges"]
                ]
            )
            st.dataframe(evidence, width="stretch", hide_index=True)


def _records(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.info("No records match the current filters.")
        return
    table = researcher_table(frame)
    if len(table.columns):
        st.dataframe(table, width="stretch", hide_index=True)
    render_record_picker(frame, "ai26_records_inspector")


def _reports(settings: Settings, frame: pd.DataFrame) -> None:
    reports = load_reports(settings.data_path("reports"))
    if not reports:
        st.info("No locally materialized periodic reports are available yet.")
        return
    labels = [
        f"{item.date.date().isoformat() if item.date else 'undated'} · {item.title}"
        for item in reports
    ]
    report = reports[labels.index(st.selectbox("Periodic report", labels))]
    st.markdown(report.body)
    if report.source_urls:
        linked = (
            frame[frame["source_url"].isin(report.source_urls)]
            if "source_url" in frame
            else frame.iloc[0:0]
        )
        st.caption(f"Evidence links visible in current filtered view: {len(linked)}")


def _rag(settings: Settings, filters: Mapping[str, Any]) -> None:
    st.caption(
        "RAG is an upstream service. This panel sends project-scoped Redis Stream requests and "
        "renders only returned evidence references."
    )
    if settings.messaging_backend != "redis" or not settings.redis_url:
        st.info("RAG messaging is disabled in this deployment.")
        return
    control = RedisAI26ControlPlane(_redis_client(settings), settings)
    history = st.session_state.setdefault("ai26_rag_history", [])
    for item in history[-20:]:
        with st.chat_message(item["role"]):
            st.write(item["content"])
            if item.get("evidence"):
                st.json(item["evidence"])
    if question := st.chat_input("Ask about analyzed AI26 data"):
        request_id = control.rag_request(question, actor="dashboard-researcher", filters=filters)
        history.append({"role": "user", "content": question, "correlation_id": request_id})
        st.session_state["ai26_rag_pending"] = request_id
        st.rerun()
    if pending := st.session_state.get("ai26_rag_pending"):
        response = control.rag_response(pending)
        if response:
            history.append(
                {
                    "role": "assistant",
                    "content": response.get("answer")
                    or response.get("text")
                    or "RAG returned a response without answer text.",
                    "evidence": response.get("evidence")
                    or response.get("sources")
                    or response.get("references")
                    or [],
                }
            )
            st.session_state.pop("ai26_rag_pending", None)
            st.rerun()
        st.info(f"Waiting for RAG response · correlation_id={pending}")


def _configuration(settings: Settings) -> None:
    st.caption(
        "Only explicitly safe Visualization settings can be proposed here. Secrets and upstream "
        "Analysis/Collection settings remain read-only."
    )
    st.json(inspect_effective_config(settings))
    if settings.messaging_backend != "redis" or not settings.redis_url:
        st.info("Redis control plane is disabled; effective configuration is read-only.")
        return
    control = RedisAI26ControlPlane(_redis_client(settings), settings)
    st.markdown("#### Distributed Visualization configuration")
    st.json(control.effective_visualization_config())
    field = st.selectbox("Mutable setting", sorted(MUTABLE_VISUALIZATION_SETTINGS))
    value = st.text_input("Proposed JSON value", value="null")
    reason = st.text_input("Reason for change")
    confirmed = st.checkbox("I confirm publishing this project-scoped configuration proposal")
    if st.button("Publish configuration proposal", disabled=not confirmed):
        request_id = control.publish_visualization_config(
            {field: json.loads(value)},
            actor="dashboard-researcher",
            reason=reason,
        )
        st.success(
            f"Published config event {request_id}. The receiving module must validate/apply it."
        )


def _hermes(settings: Settings, frame: pd.DataFrame) -> None:
    st.caption(
        "Hermes is bounded to Visualization-owned diagnostics, summaries, review requests and "
        "explicit coordination actions. No shell access is exposed here."
    )
    st.json(inspect_effective_config(settings))
    st.json({"records_in_filtered_view": len(frame), "columns": sorted(frame.columns)[:100]})
    if st.button("Clear local derived cache"):
        st.json(clear_derived_cache(settings))


def _diagnostics(settings: Settings, snapshot: LiveSnapshot, frame: pd.DataFrame) -> None:
    st.json(
        {
            "project_id": settings.project_id,
            "loaded_at": snapshot.loaded_at,
            "newest_analyzed_at": snapshot.newest_analyzed_at,
            "analyzed_age_hours": snapshot.analyzed_age_hours,
            "query_ms": snapshot.query_ms,
            "page_size": snapshot.page_size,
            "loaded_records": len(frame),
            "freshness_warning_hours": FRESHNESS_WARNING_HOURS,
            "mongo_collections": ai26_collection_names(settings),
            "redis_contract": ai26_redis_contract(settings),
            "safe_config": settings.safe_summary(),
        }
    )
    if settings.messaging_backend == "redis" and settings.redis_url:
        try:
            import redis

            status = RedisOperationalStatus(
                _redis_client(settings),
                prefix=settings.redis_key_prefix,
                heartbeat_ttl_seconds=settings.redis_heartbeat_ttl_seconds,
                event_limit=settings.redis_event_limit,
                error_types=(
                    redis.exceptions.RedisError,
                    ConnectionError,
                    OSError,
                    TimeoutError,
                    TypeError,
                    ValueError,
                ),
            ).snapshot(settings.project_id)
            st.json(
                {
                    "redis_available": status.available,
                    "workers": len(status.workers),
                    "events": len(status.events),
                    "note": status.note,
                }
            )
        except (ImportError, ConnectionError, OSError, TimeoutError, TypeError, ValueError) as exc:
            st.warning(f"Redis diagnostics unavailable: {type(exc).__name__}")
    st.caption(
        "This dashboard assumes host/network-level access control. Do not expose it to the public "
        "Internet without authentication or reverse-proxy access control."
    )


def run_demo(settings: Settings) -> None:
    """Render the public demonstration copy from an approved bundle (issue #342).

    A copy of this dashboard runs from files, not from the private database: the bundle is a
    versioned JSONL of records plus an optional AnalyticalGraph JSON, both produced by
    ``scripts/export_ai26_demo_bundle.py``. Only the read-only views are rendered — no reports,
    RAG chat, configuration, Hermes integration or host diagnostics, because those read services
    the demo must not have.
    """
    st.set_page_config(page_title="LaclauGPT AI26 Public Demo", layout="wide")
    render_header()
    st.caption("Public demonstration copy of the AI26 research dashboard · read-only")
    st.warning(CAVEAT)
    frame = _demo_frame(settings)
    if frame is None or frame.empty:
        st.error(
            "No demo bundle loaded. Set LACLAUGPT_VIS_DEMO_BUNDLE to the approved bundle file."
        )
        st.caption("A demo copy never falls back to a private database or a private endpoint.")
        return
    st.info(
        f"Demo data: {len(frame)} records · data as of {settings.demo_as_of or 'not recorded'} · "
        "DNA and SNA are experimental Phase 2 products"
    )
    filtered, _filters = _sidebar(frame)
    st.sidebar.caption("Public demo · read-only · refreshed by the operator on each release")
    renderers = (
        lambda: _explore(filtered),
        lambda: _networks(filtered, None, artifact_path=settings.demo_graph),
        lambda: _records(filtered),
    )
    for tab, renderer in zip(st.tabs(list(DEMO_TABS)), renderers, strict=True):
        with tab:
            renderer()


def _demo_frame(settings: Settings) -> pd.DataFrame | None:
    """The approved demo bundle, or ``None`` when it is missing."""
    bundle = (
        Path(settings.demo_bundle)
        if settings.demo_bundle
        else settings.data_dir / "demo" / "records.jsonl"
    )
    if not bundle.is_file():
        return None
    try:
        return load_frame(bundle, settings)
    except (OSError, ValueError):
        return None


def run() -> None:
    settings = get_settings()
    if settings.demo_mode:
        # Issue #342: a copied public demo renders the approved bundle and nothing else. The
        # research deployment below is untouched because demo mode defaults to off.
        return run_demo(settings)
    st.set_page_config(page_title="LaclauGPT AI26 Research Dashboard", layout="wide")
    render_header()
    st.caption("Live AI26 research dashboard · descriptive observations and source evidence")
    st.warning(CAVEAT)
    settings = get_settings()
    ai26_namespace(settings)
    if settings.storage != "distributed" or settings.data_backend != "mongodb":
        st.error("AI26 live dashboard requires distributed storage with MongoDB durable data.")
        return
    page_size = st.sidebar.number_input(
        "Loaded live window",
        min_value=100,
        max_value=MAX_PAGE_SIZE,
        value=DEFAULT_PAGE_SIZE,
        step=100,
    )
    st.sidebar.caption(
        "Live data is read when the page reruns. Use Refresh now to request "
        "a new snapshot; automatic background polling is not enabled."
    )
    if st.sidebar.button("Refresh now"):
        st.cache_data.clear()
    try:
        snapshot = load_ai26_snapshot(settings, limit=int(page_size))
    except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
        st.error(
            "The AI26 live data source is unavailable. Check the private MongoDB "
            "connection, dashboard credentials and service logs."
        )
        st.caption(f"Error category: {type(exc).__name__}. No research records were loaded.")
        return
    filtered, filters = _sidebar(snapshot.frame)
    st.sidebar.caption(f"Last loaded: {snapshot.loaded_at} · manual refresh")
    tabs = st.tabs(
        [
            "Monitor",
            "Explore",
            "Networks",
            "Records",
            "Reports",
            "RAG Chat",
            "Configuration",
            "Hermes",
            "Diagnostics",
        ]
    )
    renderers = (
        lambda: _monitor(snapshot, filtered),
        lambda: _explore(filtered),
        lambda: _networks(filtered, settings),
        lambda: _records(filtered),
        lambda: _reports(settings, filtered),
        lambda: _rag(settings, filters),
        lambda: _configuration(settings),
        lambda: _hermes(settings, filtered),
        lambda: _diagnostics(settings, snapshot, filtered),
    )
    for tab, renderer in zip(tabs, renderers, strict=True):
        with tab:
            renderer()


if __name__ == "__main__":
    run()
