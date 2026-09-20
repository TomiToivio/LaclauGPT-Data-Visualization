"""Streamlit research workbench for legacy, canonical-live and hybrid data."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import plotly.express as px
import streamlit as st

from .canonical import LEGACY_COLUMNS
from .config import get_settings
from .data import filter_frame, load_frame
from .ep24 import country_counts as ep24_country_counts
from .ep24 import dimension_counts as ep24_dimension_counts
from .ep24 import legacy_change_summary as ep24_legacy_change_summary
from .ep24 import load_ep24_bundle
from .ep24 import overview as ep24_overview
from .ep24 import qa_summary as ep24_qa_summary
from .graph_explorer import (
    evidence_for_edge,
    filter_explorer_graph,
    jsonld_bytes,
    plotly_network_figure,
    projection_envelope,
)
from .phase0_browser import render_phase0_browser
from .plugins import default_registry
from .plugin_pages import discover_plugin_pages, render_plugin_page
from .products import DataProduct, InMemoryProvider, ProductKind
from .provenance import (
    UNKNOWN,
    comparison_warning,
    compatibility_provenance,
    has_canonical_provenance,
    provenance_frame,
    safe_provenance_events,
    summarize_provenance,
)
from .research_views import (
    DASHBOARD_MODES,
    infer_dashboard_mode,
    load_reports,
)
from .spatiotemporal import (
    spatiotemporal_map_points,
    spatiotemporal_timeline_counts,
)
from .review import (\n    Review,\n    SQLiteReviewStore,\n    canonical_review_source_url,\n    save_canonical_review,\n)
from .storage import load_mongodb
from .transforms import explore, graph_projection, monitor, relations
from .worker_status import RedisOperationalStatus

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
    if settings.project_id.casefold() == "ep24" and settings.analysis_data_dir:
        bundle = load_ep24_bundle(settings.analysis_data_dir)
        if not bundle.records.empty:
            return bundle.records
    if settings.data_backend == "sqlite" and settings.sqlite_path.exists():
        return load_frame(settings.sqlite_path, settings)
    roots = [settings.analysis_data_dir, settings.data_dir]
    candidates: list[Path] = []
    for root in roots:
        if root and Path(root).exists():
            for suffix in ("*.jsonl", "*.ndjson", "*.csv", "*.json"):
                candidates.extend(sorted(Path(root).glob(suffix)))
    return load_frame(candidates[0], settings) if candidates else None


def _provenance_sidebar_filters(frame):
    """Filter on safe provenance projections without changing canonical records."""
    if frame.empty:
        return frame
    projected = provenance_frame(frame)
    mask = projected.index.to_series().map(lambda _value: True)
    filters = (
        ("run_id", "Run"),
        ("context_profile", "Context profile"),
        ("codebook_id", "Codebook"),
        ("codebook_version", "Codebook version"),
        ("codebook_hash", "Codebook hash"),
        ("effective_config_hash", "Config hash"),
        ("model", "Model"),
        ("backend", "Model backend"),
        ("validation_status", "Validation state"),
    )
    for field, label in filters:
        values = sorted(
            {
                str(value)
                for value in projected[field]
                if value not in (None, "", UNKNOWN)
            }
        )
        if not values:
            continue
        selected = st.sidebar.multiselect(label, values)
        if selected:
            mask &= projected[field].astype(str).isin(selected)

    rag_filter = st.sidebar.selectbox(
        "RAG/context retrieval",
        ("Any", "Enabled", "Disabled", "Unknown"),
    )
    if rag_filter != "Any":
        expected = {"Enabled": True, "Disabled": False, "Unknown": None}[rag_filter]
        mask &= projected["rag_enabled"].map(lambda value: value is expected)
    return frame.loc[mask]


def _sidebar_filters(frame):
    query = st.sidebar.text_input("Search")
    platforms = sorted(value for value in frame["source_platform"].unique() if value)
    countries = sorted(value for value in frame["source_country"].unique() if value)
    languages = sorted(value for value in frame["source_language"].unique() if value)
    formations = sorted({str(item) for values in frame["formations"] for item in values})
    entities = sorted({str(item) for values in frame["entities"] for item in values})
    topics = sorted({str(item) for values in frame["topics"] for item in values})
    signifiers = sorted({str(item) for values in frame["signifiers"] for item in values})
    frontiers = sorted({str(item) for values in frame["frontier"] for item in values})
    filtered = filter_frame(
        frame,
        query=query,
        platforms=st.sidebar.multiselect("Platforms", platforms),
        countries=st.sidebar.multiselect("Countries", countries),
        languages=st.sidebar.multiselect("Languages", languages),
        formations=st.sidebar.multiselect("Formations", formations),
        entities=st.sidebar.multiselect("Actors / entities", entities),
        topics=st.sidebar.multiselect("Themes / topics", topics),
        signifiers=st.sidebar.multiselect("Signifiers", signifiers),
        frontiers=st.sidebar.multiselect("Frontiers", frontiers),
    )
    return _provenance_sidebar_filters(filtered)


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


def _render_provenance(row) -> None:
    summary = summarize_provenance(row)
    st.markdown("#### Analysis provenance")
    if not has_canonical_provenance(row):
        compat = compatibility_provenance(row)
        st.info(
            "Canonical Phase 1 provenance is unavailable for this record. "
            "No run, model, codebook, configuration, RAG, or memory metadata is inferred."
        )
        if compat:
            st.markdown("##### Phase 0 compatibility / source-stage metadata")
            st.json(compat)
        else:
            st.caption("No compatibility/source-stage provenance metadata is recorded.")
        return

    primary = {
        "run_id": summary["run_id"],
        "study_id": summary["study_id"],
        "arena": summary["arena"],
        "dataset": summary["dataset"],
        "country": summary["country"],
        "language": summary["language"],
        "effective_config_version": summary["effective_config_version"],
        "effective_config_hash": summary["effective_config_hash"],
        "execution_profile": summary["execution_profile"],
        "context_profile": summary["context_profile"],
        "codebook_id": summary["codebook_id"],
        "codebook_version": summary["codebook_version"],
        "codebook_hash": summary["codebook_hash"],
        "model": summary["model"],
        "backend": summary["backend"],
        "task_profile": summary["task_profile"],
        "pipeline_version": summary["pipeline_version"],
        "validation_status": summary["validation_status"],
    }
    st.json(primary)

    rag_label = (
        "unknown / not recorded"
        if summary["rag_enabled"] is None
        else ("enabled" if summary["rag_enabled"] else "disabled")
    )
    memory_label = (
        "unknown / not recorded"
        if summary["context_memory_enabled"] is None
        else ("enabled" if summary["context_memory_enabled"] else "disabled")
    )
    st.caption(f"RAG/retrieval: {rag_label} · context memory: {memory_label}")

    with st.expander("Context / RAG provenance"):
        st.json(
            {
                "embedding_model": summary["embedding_model"],
                "index_version": summary["index_version"],
                "retrieval_ids": summary["retrieval_ids"],
                "context_source_refs": summary["context_source_refs"],
                "previous_summary_id": summary["previous_summary_id"],
                "collection_config_id": summary["collection_config_id"],
            }
        )
        st.caption(
            "Only safe identifiers are shown. Private prompts, codebook contents, "
            "credentials and configuration payloads are intentionally not rendered."
        )
    with st.expander("Safe provenance events"):
        events = safe_provenance_events(row)
        if events:
            st.json(events)
        else:
            st.caption("No safe provenance events recorded for this legacy/current record.")


def _review_page(frame) -> None:
    if frame.empty:
        st.info("No records in the current view.")
        return

    canonical_mask = frame.apply(
        lambda item: canonical_review_source_url(item.to_dict()) is not None,
        axis=1,
    )
    canonical_frame = frame.loc[canonical_mask]
    if canonical_frame.empty:
        st.info(
            "Researcher Review is available only for canonical Phase 1 records. "
            "Phase 0 inspection remains read-only."
        )
        return

    settings = get_settings()
    store = SQLiteReviewStore(settings.data_path("database", "reviews.sqlite3"))
    options = canonical_frame["source_url"].fillna("").astype(str).tolist()
    source_url = st.selectbox("Record", options)
    row = canonical_frame[canonical_frame["source_url"] == source_url].iloc[0]
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

    _render_provenance(row)

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
                "codebook_refs",
                "memory_refs",
                "evidence",
            )
            if key in row
        }
    )

    existing = store.get(source_url) or Review(source_url=source_url)
    statuses = ["PROVISIONAL", "ACCEPTED", "REJECTED", "REVISED", "CANONICAL", "SUPERSEDED"]
    status = st.selectbox("Review status", statuses, index=statuses.index(existing.status))
    note = st.text_area("Researcher note", value=existing.note)
    corrections_text = st.text_area(
        "Corrections (JSON object)",
        value=json.dumps(existing.corrections, ensure_ascii=False, indent=2),
    )
    dubious = st.checkbox("Dubious", value=existing.dubious)
    exclude = st.checkbox("Recommend exclusion", value=existing.exclude)
    wrong_language = st.checkbox("Wrong language", value=existing.wrong_language)
    rerun_analysis = st.checkbox("Request analysis rerun", value=existing.rerun_analysis)
    rerun_asr = st.checkbox("Request ASR rerun", value=existing.rerun_asr)
    rerun_ocr = st.checkbox("Request OCR rerun", value=existing.rerun_ocr)
    reprocess_media = st.checkbox(
        "Request media reprocessing", value=existing.reprocess_media
    )
    if st.button("Save review"):
        try:
            corrections = json.loads(corrections_text or "{}")
            if not isinstance(corrections, dict):
                raise ValueError("Corrections must be a JSON object.")
        except (json.JSONDecodeError, ValueError) as exc:
            st.error(f"Review not saved: {exc}")
            return

        review = Review(
            source_url=source_url,
            reviewer=existing.reviewer,
            status=status,
            note=note,
            dubious=dubious,
            exclude=exclude,
            wrong_language=wrong_language,
            corrections=corrections,
            rerun_analysis=rerun_analysis,
            rerun_asr=rerun_asr,
            rerun_ocr=rerun_ocr,
            reprocess_media=reprocess_media,
            split_request=existing.split_request,
            cut_request=existing.cut_request,
            review_version=existing.review_version + 1,
        )
        save_canonical_review(row.to_dict(), review, store)
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


def _graph_explorer_page(frame) -> None:
    """Phase-1 source/provenance/Laclau graph explorer over the shared graph contract."""
    st.markdown("#### RDF / knowledge graph explorer")
    st.caption(
        "A bounded research view over the backend-neutral laclaugpt.graph.v1 contract. "
        "Phase 1 exposes source/provenance and Laclau layers; DNA/SNA stay gated to Phase 2."
    )

    controls = st.columns([2, 1, 1, 1])
    query = controls[0].text_input("Graph search", key="graph_search")
    max_nodes = controls[1].number_input(
        "Max nodes", min_value=10, max_value=1000, value=250, step=10
    )
    max_edges = controls[2].number_input(
        "Max edges", min_value=10, max_value=2500, value=500, step=10
    )
    min_weight = controls[3].number_input(
        "Min edge weight", min_value=0.0, value=0.0, step=0.5
    )

    temporal_enabled = st.checkbox(
        "Temporal window",
        value=False,
        help=(
            "Slice the graph using one explicit recorded clock. Missing timestamps are excluded; "
            "Visualization never substitutes another clock."
        ),
    )
    clock = None
    start = None
    end = None
    if temporal_enabled:
        temporal_controls = st.columns([1, 2, 2])
        clock = temporal_controls[0].selectbox(
            "Clock",
            ["source", "collection", "analysis"],
            help="Source, collection and analysis time are distinct canonical clocks.",
        )
        start = temporal_controls[1].text_input(
            "Window start (ISO-8601, inclusive)",
            key="graph_temporal_start",
            placeholder="2026-09-01T00:00:00Z",
        )
        end = temporal_controls[2].text_input(
            "Window end (ISO-8601, inclusive)",
            key="graph_temporal_end",
            placeholder="2026-09-30T23:59:59Z",
        )

    try:
        graph = projection_envelope(
            frame,
            max_nodes=int(max_nodes),
            max_edges=int(max_edges),
            clock=clock,
            start=start,
            end=end,
        )
    except ValueError as exc:
        st.error(f"Temporal graph window is invalid: {exc}")
        return

    temporal = graph.metadata.get("temporal")
    if temporal:
        st.caption(
            "Temporal graph uses "
            f"{temporal['clock']} time only · "
            f"{temporal['records_in_window']} records in window · "
            f"{temporal['records_missing_timestamp']} records missing that clock. "
            "Window boundaries are inclusive."
        )

    node_types = sorted({str(node.get("type")) for node in graph.nodes})
    edge_types = sorted({str(edge.get("type")) for edge in graph.edges})

    filter_cols = st.columns(3)
    selected_layers = filter_cols[0].multiselect(
        "Layers",
        ["source", "provenance", "laclau"],
        default=["source", "provenance", "laclau"],
    )
    selected_nodes = filter_cols[1].multiselect("Node types", node_types)
    selected_edges = filter_cols[2].multiselect("Edge types", edge_types)

    visible = filter_explorer_graph(
        graph,
        query=query,
        node_types=selected_nodes,
        edge_types=selected_edges,
        layers=selected_layers,
        min_weight=float(min_weight),
    )
    metrics = st.columns(4)
    metrics[0].metric("Visible nodes", len(visible.nodes))
    metrics[1].metric("Visible edges", len(visible.edges))
    metrics[2].metric("Backend", str(visible.metadata.get("backend", "unknown")))
    metrics[3].metric("Truncated", "yes" if visible.truncated else "no")

    if not visible.nodes:
        st.info("No graph nodes match the current filters.")
        return

    st.plotly_chart(plotly_network_figure(visible), use_container_width=True)
    st.caption(
        "Layout distance and degree are navigational aids only. They do not establish "
        "nodal status, hegemony, equivalence, antagonism, polarization or ideological formation."
    )

    edge_lookup = {
        f"{edge.get('source')} → {edge.get('target')} · {edge.get('type')}": edge
        for edge in visible.edges
    }
    if edge_lookup:
        st.markdown("##### Evidence / provenance inspector")
        selected = st.selectbox("Relation", list(edge_lookup), key="graph_relation")
        st.json(evidence_for_edge(edge_lookup[selected]))

    left, right = st.columns(2)
    with left:
        st.download_button(
            "Export visible subgraph as JSON-LD",
            data=jsonld_bytes(visible),
            file_name="laclaugpt-subgraph.jsonld",
            mime="application/ld+json",
        )
    with right:
        st.caption(
            "Turtle export remains provider-dependent; JSON-LD is available for every "
            "backend-neutral graph payload."
        )

    with st.expander("Inspect graph contract payload"):
        st.json(visible.as_dict())


def _research_data_page(frame) -> None:
    st.markdown("#### Full researcher dataframe")
    st.caption(
        "This table intentionally includes legacy EP24 aliases, intermediate stage outputs, "
        "new LaclauGPT fields and safe provenance projections."
    )
    provenance = provenance_frame(frame).add_prefix("prov_")
    display = frame.join(provenance)
    if "provenance" in display:
        display["provenance"] = [
            safe_provenance_events(row)
            for row in frame.to_dict(orient="records")
        ]
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
        "prov_run_id",
        "prov_context_profile",
        "prov_codebook_id",
        "prov_codebook_version",
        "prov_codebook_hash",
        "prov_effective_config_hash",
        "prov_model",
        "prov_backend",
        "prov_rag_enabled",
        "prov_validation_status",
        "raw_ref",
        "review_status",
    ]
    ordered = [column for column in preferred if column in display.columns]
    ordered.extend(column for column in display.columns if column not in ordered)
    st.dataframe(display[ordered], use_container_width=True, hide_index=True)


def _timeline_map_page(frame) -> None:
    st.markdown("#### Timeline")
    counts = spatiotemporal_timeline_counts(frame)
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
            "Source, collection, analysis and evidence-backed event clocks remain separate. "
            "Missing times are disabled rather than substituted."
        )

    st.markdown("#### Map")
    points = spatiotemporal_map_points(frame)
    if points.empty:
        st.caption(
            "No evidence-backed geospatial observations in this view. Missing, inferred, "
            "unvalidated geocoded and partial coordinates are disabled rather than repaired."
        )
    else:
        st.plotly_chart(
            px.scatter_geo(
                points,
                lat="latitude",
                lon="longitude",
                hover_name="label",
                hover_data=["location", "event_type", "source_url"],
                title="Evidence-backed source/event geography",
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
    st.caption(
        "Generated reports are research aids and require human verification before citation as findings."
    )



def _ep24_improved_page(frame) -> None:
    """Research views for the improved #245 Finland/Poland handoff."""
    settings = get_settings()
    bundle = load_ep24_bundle(settings.analysis_data_dir or settings.data_dir)
    values = ep24_overview(frame, bundle.failures)

    st.markdown("#### EP24 improved Finland / Poland analysis")
    st.caption(
        "Local-file research view for Data-Analysis #245. Source, legacy, "
        "researcher-grounded and model-derived values remain inspectable rather than "
        "being flattened into a single score."
    )
    metrics = st.columns(6)
    metrics[0].metric("Documents", values["documents"])
    metrics[1].metric("Finland", values["finland"])
    metrics[2].metric("Poland", values["poland"])
    metrics[3].metric("Analyzed", values["analyzed"])
    metrics[4].metric("Failures", values["failures"])
    metrics[5].metric("Codebook refs", values["codebook_refs"])
    st.caption(
        f"Storage: {bundle.storage_kind}"
        + (f" · {bundle.source_path}" if bundle.source_path else " · no #245 bundle found")
    )

    countries = ep24_country_counts(frame)
    if not countries.empty:
        st.plotly_chart(
            px.bar(countries, x="country", y="documents", title="Country coverage"),
            use_container_width=True,
        )

    dimensions = {
        "Signifiers": "signifiers",
        "Nodal points": "nodal_points",
        "Actors / entities": "entities",
        "Themes / topics": "topics",
        "Frontiers": "frontier",
        "Affects": "affects",
    }
    for tab, (title, field) in zip(st.tabs(list(dimensions)), dimensions.items(), strict=True):
        with tab:
            table = ep24_dimension_counts(frame, field)
            if table.empty:
                st.caption(f"No {title.lower()} exported in the current view.")
            else:
                st.dataframe(table.head(200), use_container_width=True, hide_index=True)
                st.plotly_chart(
                    px.bar(
                        table.groupby(["country", field], as_index=False)["count"].sum()
                        .sort_values("count", ascending=False)
                        .head(40),
                        x="count",
                        y=field,
                        color="country",
                        orientation="h",
                        barmode="group",
                        title=f"{title}: Finland / Poland",
                    ),
                    use_container_width=True,
                )

    st.markdown("#### Relations")
    relation_table = relations(frame)
    if relation_table.empty:
        st.caption("No relation edges exported in the current view.")
    else:
        st.dataframe(relation_table.head(500), use_container_width=True, hide_index=True)
        st.caption("The edge table is primary; graph layout is descriptive, not theoretical proof.")

    st.markdown("#### Legacy vs improved")
    if bundle.legacy_comparison.empty:
        st.caption("legacy_comparison.csv is not present in the current #245 handoff.")
    else:
        summary = ep24_legacy_change_summary(bundle.legacy_comparison)
        st.dataframe(summary, use_container_width=True, hide_index=True)
        with st.expander("Inspect comparison rows"):
            st.dataframe(bundle.legacy_comparison.head(1000), use_container_width=True, hide_index=True)

    st.markdown("#### QA / provenance")
    st.dataframe(
        ep24_qa_summary(frame, bundle.failures),
        use_container_width=True,
        hide_index=True,
    )
    if not bundle.failures.empty:
        with st.expander("Failed rows / stages"):
            st.dataframe(bundle.failures.head(1000), use_container_width=True, hide_index=True)
    st.caption(CAVEAT)


def _run_ids(frame) -> set[str]:
    if frame.empty:
        return set()
    projected = provenance_frame(frame)
    if "run_id" not in projected:
        return set()
    return {
        str(value)
        for value in projected["run_id"]
        if value not in (None, "", UNKNOWN)
    }


def _live_status_page(frame) -> None:
    """Best-effort transient Redis view; durable research state never depends on it."""
    settings = get_settings()
    st.markdown("#### Live worker and workflow status")
    st.caption(
        "This panel is transient operational telemetry, not research data or audit history. "
        "Durable records and results remain available independently of Redis."
    )
    if settings.messaging_backend != "redis":
        st.info("Live Redis status is disabled. Durable dashboard data is fully available.")
        return
    if not settings.redis_url:
        st.warning("Live Redis status is unavailable because no private runtime Redis URL is configured.")
        return
    try:
        import redis
    except ImportError:
        st.warning("Live Redis status is unavailable because the optional Redis client is not installed.")
        return

    try:
        client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
            decode_responses=False,
        )
    except ValueError:
        st.warning("Live Redis status is unavailable because the private runtime Redis URL is invalid.")
        return

    status = RedisOperationalStatus(
        client,
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
    ).snapshot(settings.project_id, run_ids=_run_ids(frame))

    if not status.available:
        st.warning(status.note)
        return

    workers = [
        {
            "worker_id": item.worker_id,
            "role": item.worker_role,
            "run_id": item.run_id,
            "state": "stale" if item.stale else item.status,
            "reported_state": item.status,
            "task_id": item.current_task_id or "",
            "age_seconds": round(item.age_seconds, 1),
            "updated_at": item.updated_at.isoformat(),
        }
        for item in status.workers
    ]
    if workers:
        st.markdown("##### Workers")
        st.dataframe(workers, use_container_width=True, hide_index=True)
    else:
        st.caption("No matching worker heartbeats are currently visible.")

    events = [
        {
            "stream": item.stream,
            "message_id": item.message_id or "",
            "task_id": item.task_id or "",
            "run_id": item.run_id or "",
            "task_type": item.task_type or "",
            "producer": item.producer or "",
            "created_at": item.created_at or "",
        }
        for item in status.events
    ]
    if events:
        st.markdown("##### Recent safe workflow identifiers")
        st.dataframe(events, use_container_width=True, hide_index=True)
        st.caption("Queue payloads and arbitrary event metadata are intentionally not rendered.")
    st.caption(status.note)


def _plugin_provider(frame) -> InMemoryProvider:
    """Expose products already present in the dashboard without performing new analysis."""
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
    if settings.messaging_backend == "redis" and settings.redis_url:
        capabilities.add("redis_status")
    if settings.object_backend == "s3" and settings.s3_bucket:
        capabilities.add("allas")
    return capabilities



def _activate_builtin_plugin_renderers(registry) -> None:
    """Bind maintained Phase-1 views to matching plugin contracts."""

    def render_table(products, context):
        st.dataframe(
            products[ProductKind.TABLE].payload,
            use_container_width=True,
            hide_index=True,
        )

    def render_timeline(products, context):
        timeline = products[ProductKind.TIMELINE].payload
        st.plotly_chart(
            px.line(
                timeline,
                x="period",
                y="documents",
                color="time_kind",
                markers=True,
            ),
            use_container_width=True,
        )

    def render_map(products, context):
        points = products[ProductKind.GEODATA].payload
        st.plotly_chart(
            px.scatter_geo(
                points,
                lat="latitude",
                lon="longitude",
                hover_name="label",
                hover_data=["location", "event_type", "source_url"],
            ),
            use_container_width=True,
        )

    def render_network(products, context):
        network = products[ProductKind.NETWORK].payload
        st.caption(
            f"Plugin graph: {len(network.get('nodes', []))} nodes, "
            f"{len(network.get('edges', []))} edges"
        )
        st.json(network)

    for name, renderer in {
        "table": render_table,
        "timeline": render_timeline,
        "map": render_map,
        "network": render_network,
    }.items():
        try:
            registry.get(name).render = renderer
        except KeyError:
            continue


def _plugin_driven_tabs(frame, mode: str):
    """Build optional tabs without making core browsing depend on plugins."""
    try:
        registry = default_registry()
        _activate_builtin_plugin_renderers(registry)
        provider = _plugin_provider(frame)
        plugin_pages = discover_plugin_pages(
            registry,
            provider,
            rag_enabled=ProductKind.RETRIEVAL in provider.capabilities(),
            backend_capabilities=_backend_capabilities(),
            fields=set(frame.columns),
            mode=mode,
        )
    except Exception:
        return [], []

    labels = []
    pages = []
    for plugin_page in plugin_pages:
        labels.append(f"Plugin · {plugin_page.title}")

        def render_optional(current_frame, page=plugin_page, current_registry=registry):
            current_provider = _plugin_provider(current_frame)
            result = render_plugin_page(
                current_registry,
                page,
                current_provider,
                context={"mode": mode},
                project=get_settings().project_id,
            )
            if not result.ok:
                st.warning(
                    f"Optional plugin {page.plugin.spec.name!r} failed and was isolated: "
                    f"{result.error}"
                )

        pages.append(render_optional)
    return labels, pages


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
    warning = comparison_warning(frame)
    if warning:
        st.warning(warning)
    if mode == "legacy_ep24":
        labels = ["Researcher Review", "Research Data", "Timeline & Map", "Reports"]
        pages = [_review_page, _research_data_page, _timeline_map_page, _reports_page]
    elif mode == "canonical_live":
        labels = [
            "Monitor",
            "Explore",
            "Graph Explorer",
            "Researcher Review",
            "Timeline & Map",
            "Reports",
            "Research Data",
        ]
        pages = [
            _monitor_page,
            _explore_page,
            _graph_explorer_page,
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
            "Graph Explorer",
            "Timeline & Map",
            "Reports",
            "Research Data",
        ]
        pages = [
            _monitor_page,
            _review_page,
            _explore_page,
            _graph_explorer_page,
            _timeline_map_page,
            _reports_page,
            _research_data_page,
        ]
    if get_settings().project_id.casefold() == "ep24":
        labels.insert(0, "EP24 Improved")
        pages.insert(0, _ep24_improved_page)
    labels.extend(["Live Status", "Plugin Library"])
    pages.extend([_live_status_page, lambda current_frame: _plugin_library_page(current_frame, mode)])
    plugin_labels, plugin_pages = _plugin_driven_tabs(frame, mode)
    labels.extend(plugin_labels)
    pages.extend(plugin_pages)
    for tab, page in zip(st.tabs(labels), pages, strict=True):
        with tab:
            page(frame)


def run() -> None:
    st.set_page_config(page_title="LaclauGPT Data Visualization", layout="wide")
    st.title("LaclauGPT Data Visualization")
    st.caption("Canonical live + improved/legacy EP24 + hybrid researcher workbench.")
    st.warning(CAVEAT)
    settings = get_settings()
    settings.ensure_local_directories()
    if settings.phase0_browser_enabled:
        entry = st.sidebar.radio("Application", ("Workbench", "Phase 0 browser"))
        if entry == "Phase 0 browser":
            render_phase0_browser(st, settings)
            return
    frame = _load_default_frame()
    uploaded = st.sidebar.file_uploader(
        "Open CSV, JSON or JSONL",
        type=["csv", "json", "jsonl", "ndjson"],
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
