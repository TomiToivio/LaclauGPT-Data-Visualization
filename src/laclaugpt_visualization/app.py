"""Streamlit research workbench for legacy, canonical-live and hybrid data."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import plotly.express as px
import streamlit as st

from .canonical import LEGACY_COLUMNS
from .config import get_settings
from .data import filter_frame, load_frame
from .plugins import default_registry
from .products import DataProduct, InMemoryProvider, ProductKind
from .research_views import (
    DASHBOARD_MODES,
    infer_dashboard_mode,
    load_reports,
    map_points,
    timeline_counts,
)
from .review import Review, SQLiteReviewStore
from .storage import load_mongodb
from .transforms import explore, graph_projection, monitor, relations

CAVEAT = (
    "Counts, confidence, graph degree and layout are descriptive aids. They do not by "
    "themselves establish hegemony, nodal status, empty/floating signification, antagonism "
    "or theoretical validity. Inspect evidence and human review state."
)

MODE_HELP = {
    "legacy_ep24": "Historical EP24 dataframe/researcher workflow with legacy intermediate fields.",
    "canonical_live": "Canonical near-real-time monitoring and discourse exploration.",
    "hybrid_research": "EP24-style evidence inspection plus current LaclauGPT discourse views.",
}


def _load_default_frame():
    settings = get_settings()
    settings.ensure_local_directories()
    if settings.data_backend == "mongodb":
        return load_mongodb(settings)
    if settings.data_backend == "sqlite" and settings.sqlite_path.exists():
        return load_frame(settings.sqlite_path, settings)
    roots = [settings.analysis_data_dir, settings.data_dir]
    candidates: list[Path] = []
    for root in roots:
        if root and Path(root).exists():
            for suffix in ("*.jsonl", "*.ndjson", "*.csv", "*.json"):
                candidates.extend(sorted(Path(root).glob(suffix)))
    return load_frame(candidates[0], settings) if candidates else None


def _sidebar_filters(frame):
    query = st.sidebar.text_input("Search")
    platforms = sorted(value for value in frame["source_platform"].unique() if value)
    countries = sorted(value for value in frame["source_country"].unique() if value)
    languages = sorted(value for value in frame["source_language"].unique() if value)
    formations = sorted({str(item) for values in frame["formations"] for item in values})
    return filter_frame(
        frame,
        query=query,
        platforms=st.sidebar.multiselect("Platforms", platforms),
        countries=st.sidebar.multiselect("Countries", countries),
        languages=st.sidebar.multiselect("Languages", languages),
        formations=st.sidebar.multiselect("Formations", formations),
    )


def _monitor_page(frame) -> None:
    values = monitor(frame)
    cols = st.columns(5)
    cols[0].metric("Documents", values["documents"])
    cols[1].metric("Analyzed", values["analyzed"])
    cols[2].metric("Awaiting analysis", values["awaiting_analysis"])
    cols[3].metric("Latest source", values["latest_source"] or "n/a")
    cols[4].metric("Latest analysis", values["latest_analysis"] or "n/a")
    for key, title in (
        ("formations", "Formations"),
        ("signifiers", "Signifiers"),
        ("actors", "Actors"),
    ):
        table = values[key]
        if not table.empty:
            label_column = table.columns[0]
            st.plotly_chart(
                px.bar(table.head(20), x="count", y=label_column, orientation="h", title=title),
                use_container_width=True,
            )
    st.caption(CAVEAT)


def _nonempty_legacy(row: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in LEGACY_COLUMNS:
        if key not in row:
            continue
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, float) and str(value) == "nan":
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        if not isinstance(value, (list, dict)) and not str(value).strip():
            continue
        values[key] = value
    return values


def _review_page(frame) -> None:
    if frame.empty:
        st.info("No records in the current view.")
        return
    settings = get_settings()
    store = SQLiteReviewStore(settings.data_path("database", "reviews.sqlite3"))
    options = frame["source_url"].fillna("").astype(str).tolist()
    source_url = st.selectbox("Record", options)
    row = frame[frame["source_url"] == source_url].iloc[0]
    st.subheader(row.get("summary") or row.get("human_readable_summary") or source_url)
    st.caption(f"{row.get('source_platform', '')} · {row.get('source_author', '')}")

    researcher_report = str(row.get("human_readable_markdown") or "")
    if researcher_report:
        st.markdown("#### Human-readable research report")
        st.markdown(researcher_report)

    st.markdown("#### Whisper / ASR transcript")
    st.text(row.get("whisper_transcript") or row.get("transcript") or "No transcript")
    if row.get("whisper_translated"):
        st.markdown("#### Whisper translation")
        st.text(row.get("whisper_translated"))
    if row.get("ocr"):
        st.markdown("#### OCR")
        st.write(row.get("ocr"))
    if row.get("frame_analysis") or row.get("frames"):
        st.markdown("#### Multimodal / frame analysis")
        st.write(row.get("frame_analysis") or row.get("frames"))

    legacy_values = _nonempty_legacy(row)
    st.markdown("#### Legacy researcher fields")
    if legacy_values:
        st.json(legacy_values)
    else:
        st.caption("No populated legacy aliases for this record.")

    with st.expander("Raw collected/scraped material"):
        raw_record = row.get("raw_record")
        raw_capture = (
            raw_record.get("raw_capture")
            if isinstance(raw_record, dict)
            else row.get("raw_capture")
        )
        st.json(raw_capture or {"raw_ref": row.get("raw_ref", "")})
    with st.expander("Intermediate stage outputs"):
        st.json(row.get("intermediate") or {})

    st.markdown("#### New structured LaclauGPT analysis")
    st.json(
        {
            key: row.get(key)
            for key in (
                "entities",
                "entity_mentions",
                "topics",
                "classifications",
                "formations",
                "signifiers",
                "nodal_points",
                "discourses",
                "imaginaries",
                "us",
                "them",
                "frontier",
                "affects",
                "sentiment_labels",
                "formula_of_populism",
                "relations",
                "uncertainties",
                "abstentions",
                "model_runs",
                "evidence",
                "provenance",
            )
            if key in row
        }
    )

    existing = store.get(source_url) or Review(source_url=source_url)
    statuses = ["PROVISIONAL", "ACCEPTED", "REJECTED", "REVISED", "CANONICAL", "SUPERSEDED"]
    status = st.selectbox("Review status", statuses, index=statuses.index(existing.status))
    note = st.text_area("Researcher note", value=existing.note)
    dubious = st.checkbox("Dubious", value=existing.dubious)
    exclude = st.checkbox("Recommend exclusion", value=existing.exclude)
    wrong_language = st.checkbox("Wrong language", value=existing.wrong_language)
    rerun_analysis = st.checkbox("Request analysis rerun", value=existing.rerun_analysis)
    rerun_asr = st.checkbox("Request ASR rerun", value=existing.rerun_asr)
    rerun_ocr = st.checkbox("Request OCR rerun", value=existing.rerun_ocr)
    if st.button("Save review"):
        store.save(
            Review(
                source_url=source_url,
                reviewer=existing.reviewer,
                status=status,
                note=note,
                dubious=dubious,
                exclude=exclude,
                wrong_language=wrong_language,
                corrections=existing.corrections,
                rerun_analysis=rerun_analysis,
                rerun_asr=rerun_asr,
                rerun_ocr=rerun_ocr,
                reprocess_media=existing.reprocess_media,
                split_request=existing.split_request,
                cut_request=existing.cut_request,
                review_version=existing.review_version + 1,
            )
        )
        st.success("Review saved to the private local review store.")


def _explore_page(frame) -> None:
    views = explore(frame)
    timeline = views["timeline"]
    if not timeline.empty:
        st.plotly_chart(
            px.line(timeline, x="period", y="documents", markers=True),
            use_container_width=True,
        )
    columns = st.columns(3)
    for target, column in zip(("formations", "topics", "entities"), columns, strict=True):
        table = views[target].head(20)
        if not table.empty:
            column.dataframe(table, use_container_width=True, hide_index=True)
    relation_table = relations(frame)
    if not relation_table.empty:
        st.markdown("#### Relations")
        st.dataframe(relation_table, use_container_width=True, hide_index=True)
    projection = graph_projection(frame)
    st.caption(
        f"Graph projection: {len(projection['nodes'])} nodes, {len(projection['edges'])} edges"
    )
    st.caption(CAVEAT)


def _research_data_page(frame) -> None:
    st.markdown("#### Full researcher dataframe")
    st.caption(
        "This table intentionally includes legacy EP24 aliases, intermediate stage outputs, "
        "new LaclauGPT fields and the human-readable report fields."
    )
    preferred = [
        "source_url",
        "recording_date",
        "country",
        "author_username",
        "source_type",
        "summary_analysis",
        "human_readable_summary",
        "whisper_transcript",
        "whisper_language",
        "whisper_translated",
        "ocr_1",
        "frame_1",
        "new_entity",
        "new_theme",
        "entities",
        "topics",
        "formations",
        "signifiers",
        "discourses",
        "formula_of_populism_analysis",
        "raw_ref",
        "review_status",
    ]
    ordered = [column for column in preferred if column in frame.columns]
    ordered.extend(column for column in frame.columns if column not in ordered)
    st.dataframe(frame[ordered], use_container_width=True, hide_index=True)


def _timeline_map_page(frame) -> None:
    st.markdown("#### Timeline")
    counts = timeline_counts(frame)
    if counts.empty:
        st.caption("No valid source, collection, analysis or event timestamps in this view.")
    else:
        st.plotly_chart(
            px.line(
                counts,
                x="period",
                y="documents",
                color="time_kind",
                markers=True,
                title="Source / collection / analysis / event time",
            ),
            use_container_width=True,
        )
        st.caption(
            "The four clocks remain separate; inferred event time is not source publication time."
        )

    st.markdown("#### Map")
    points = map_points(frame)
    if points.empty:
        st.caption("No valid geospatial observations in this view. Coordinates are never fabricated.")
    else:
        st.plotly_chart(
            px.scatter_geo(
                points,
                lat="latitude",
                lon="longitude",
                hover_name="label",
                hover_data=["location", "event_type", "source_url"],
                title="Geocoded source/event evidence",
            ),
            use_container_width=True,
        )
        st.dataframe(
            points[["source_url", "label", "location", "event_type", "event_time"]],
            use_container_width=True,
            hide_index=True,
        )


def _reports_page(frame) -> None:
    settings = get_settings()
    reports = load_reports(settings.data_path("reports"))
    if not reports:
        st.info("No generated reports found under data/reports/. Markdown and JSON reports are supported.")
        return
    labels = [
        f"{report.date.date().isoformat() if report.date is not None else 'undated'} · {report.title}"
        for report in reports
    ]
    selected = reports[labels.index(st.selectbox("Research report", labels))]
    st.markdown(selected.body)
    if selected.source_urls:
        linked = frame[frame["source_url"].isin(selected.source_urls)]
        st.caption(f"Linked records in current view: {len(linked)} / {len(selected.source_urls)}")
        if not linked.empty:
            st.dataframe(
                linked[
                    [
                        column
                        for column in ("source_url", "source_author", "summary")
                        if column in linked
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )
    st.caption("Generated reports are research aids and require human verification before citation as findings.")


def _plugin_provider(frame) -> InMemoryProvider:
    """Expose products already present in the maintained dashboard without new inference."""

    products = {
        ProductKind.TABLE: DataProduct(ProductKind.TABLE, frame),
        ProductKind.RECORDS: DataProduct(ProductKind.RECORDS, frame),
    }
    timeline = timeline_counts(frame)
    if not timeline.empty:
        products[ProductKind.TIMELINE] = DataProduct(ProductKind.TIMELINE, timeline)
    points = map_points(frame)
    if not points.empty:
        products[ProductKind.GEODATA] = DataProduct(ProductKind.GEODATA, points)
    projection = graph_projection(frame)
    if projection["nodes"] or projection["edges"]:
        products[ProductKind.NETWORK] = DataProduct(ProductKind.NETWORK, projection)
    reports = load_reports(get_settings().data_path("reports"))
    if reports:
        products[ProductKind.REPORT] = DataProduct(ProductKind.REPORT, reports)
    media_columns = {"frames", "frame_analysis", "video_file", "audio_file", "media"}
    if media_columns.intersection(frame.columns):
        products[ProductKind.MEDIA] = DataProduct(ProductKind.MEDIA, frame)
    return InMemoryProvider(products)


def _backend_capabilities() -> set[str]:
    settings = get_settings()
    capabilities: set[str] = set()
    if settings.data_backend == "mongodb" and settings.mongodb_uri:
        capabilities.add("mongodb")
    if settings.cache_backend == "redis" and settings.redis_url:
        capabilities.update({"redis_config", "redis_task_queue", "redis_message_queue"})
    if settings.object_backend == "s3" and settings.s3_bucket:
        capabilities.add("allas")
    return capabilities


def _plugin_library_page(frame, mode: str) -> None:
    st.markdown("#### Plugin library")
    st.caption(
        "Visualization plugins are read-only. User-interface plugins may edit or enqueue work "
        "only through explicit permission/audit service boundaries."
    )
    registry = default_registry()
    provider = _plugin_provider(frame)
    backends = _backend_capabilities()
    fields = set(frame.columns)
    rows = []
    for plugin in registry.all():
        status = registry.status(
            plugin.spec.name,
            provider,
            rag_enabled=ProductKind.RETRIEVAL in provider.capabilities(),
            backend_capabilities=backends,
            fields=fields,
            mode=mode,
        )
        rows.append(
            {
                "plugin": plugin.spec.name,
                "kind": plugin.spec.kind.value,
                "category": plugin.spec.category.value,
                "status": "available" if status.available else "unavailable",
                "placeholder": plugin.spec.placeholder,
                "mutates_state": plugin.spec.mutates_state,
                "requires_backends": ", ".join(sorted(plugin.spec.required_backends)),
                "reason": "; ".join(status.reasons),
                "source": plugin.spec.source or "",
            }
        )
    kind = st.selectbox("Plugin kind", ["all", "visualization", "user_interface"])
    shown = rows if kind == "all" else [row for row in rows if row["kind"] == kind]
    st.dataframe(shown, use_container_width=True, hide_index=True)
    st.caption(
        "Unavailable optional plugins are capability-gated rather than crashing local/offline mode. "
        "Placeholders describe planned contracts; they do not fabricate missing analysis products."
    )


def _render_mode(frame, mode: str) -> None:
    if mode == "legacy_ep24":
        labels = ["Researcher Review", "Research Data", "Timeline & Map", "Reports"]
        pages = [_review_page, _research_data_page, _timeline_map_page, _reports_page]
    elif mode == "canonical_live":
        labels = [
            "Monitor",
            "Explore",
            "Researcher Review",
            "Timeline & Map",
            "Reports",
            "Research Data",
        ]
        pages = [
            _monitor_page,
            _explore_page,
            _review_page,
            _timeline_map_page,
            _reports_page,
            _research_data_page,
        ]
    else:
        labels = [
            "Monitor",
            "Researcher Review",
            "Explore",
            "Timeline & Map",
            "Reports",
            "Research Data",
        ]
        pages = [
            _monitor_page,
            _review_page,
            _explore_page,
            _timeline_map_page,
            _reports_page,
            _research_data_page,
        ]
    labels.append("Plugin Library")
    pages.append(lambda current_frame: _plugin_library_page(current_frame, mode))
    for tab, page in zip(st.tabs(labels), pages, strict=True):
        with tab:
            page(frame)


def run() -> None:
    st.set_page_config(page_title="LaclauGPT Data Visualization", layout="wide")
    st.title("LaclauGPT Data Visualization")
    st.caption("Legacy EP24 + canonical live + hybrid researcher workbench.")
    st.warning(CAVEAT)
    settings = get_settings()
    settings.ensure_local_directories()
    frame = _load_default_frame()
    uploaded = st.sidebar.file_uploader(
        "Open CSV, JSON or JSONL", type=["csv", "json", "jsonl", "ndjson"]
    )
    if uploaded is not None:
        temp = settings.data_path("tmp", "uploads", uploaded.name)
        temp.parent.mkdir(parents=True, exist_ok=True)
        temp.write_bytes(uploaded.getvalue())
        frame = load_frame(temp)
    if frame is None or frame.empty:
        st.info("Add canonical/legacy CSV or JSONL under data/, configure SQLite, or configure MongoDB.")
        return

    default_mode = infer_dashboard_mode(frame)
    mode = st.sidebar.selectbox(
        "Dashboard mode",
        DASHBOARD_MODES,
        index=DASHBOARD_MODES.index(default_mode),
        format_func=lambda value: value.replace("_", " ").title(),
    )
    st.sidebar.caption(MODE_HELP[mode])
    filtered = _sidebar_filters(frame)
    _render_mode(filtered, mode)


if __name__ == "__main__":
    run()
