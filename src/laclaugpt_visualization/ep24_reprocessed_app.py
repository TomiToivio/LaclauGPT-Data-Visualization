"""Standalone EP24 Reprocessed Streamlit app (AI26 entrypoint unchanged).

Launch: streamlit run src/laclaugpt_visualization/ep24_reprocessed_app.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Run from anywhere: `streamlit run src/laclaugpt_visualization/ep24_reprocessed_app.py` puts the
# package directory (not src/) on sys.path, so make the package importable explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:  # normal case: the package is importable (development, pip install -e .)
    from laclaugpt_visualization.demo_auth import require_demo_password
    from laclaugpt_visualization.ep24_legacy_parity import (
        apply_filters,
        child_counts,
        child_counts_over_time,
        duration_by,
        frequency_by,
        language_counts,
        load_children,
        parity_rows,
        record_tabs,
        sentiment_counts,
        unsupported_tabs,
    )
    from laclaugpt_visualization.ep24_reprocessed import (
        SCHEMA_VERSION,
        STAGES,
        coverage_rows,
        dna_evidence,
        exported_counts,
        identity,
        manifest_counts_rows,
        manifest_provenance,
        missing_countries,
        multilayer,
        rdf_files,
        read_manifest,
        read_records,
        rows,
        status,
        text,
        unpack,
    )
except ModuleNotFoundError:  # standalone deployment: only this module was shipped
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from demo_auth import require_demo_password  # type: ignore[no-redef]
    from ep24_legacy_parity import (  # type: ignore[no-redef]
        apply_filters,
        child_counts,
        child_counts_over_time,
        duration_by,
        frequency_by,
        language_counts,
        load_children,
        parity_rows,
        record_tabs,
        sentiment_counts,
        unsupported_tabs,
    )
    from ep24_reprocessed import (  # type: ignore[no-redef]
        SCHEMA_VERSION,
        STAGES,
        coverage_rows,
        dna_evidence,
        exported_counts,
        identity,
        missing_countries,
        multilayer,
        rdf_files,
        read_manifest,
        read_records,
        rows,
        status,
        text,
        unpack,
    )

from laclaugpt_visualization.ep24_presentation import (
    readable,
    render_browser,
    render_inspector,
    render_overview,
    researcher_csv,
)

st.set_page_config(page_title="EP24 Reprocessed", layout="wide")
# Security gate (#62): if LACLAUGPT_VIS_DEMO_PASSWORD is set, nothing is read until it is entered.
require_demo_password()
st.title("EP24 Reprocessed · research explorer")
st.caption("Read-only multimodal pipeline evidence | Separate from AI26 | " + SCHEMA_VERSION)
root = os.environ.get("LACLAUGPT_VIS_ANALYSIS_DATA_DIR", "data")
st.sidebar.caption("Read-only data root configured by the server operator.")
frame = read_records(root)
corpus_total = len(frame)
manifest = read_manifest(root)
if manifest:
    cohort = manifest.get("approved_cohort")
    if cohort:
        st.caption("Approved cohort: " + str(cohort.get("dataset"))
                   + " · roster SHA256: " + str(cohort.get("sha256")))
        if any(cohort.get("missing_counts", {}).values()):
            st.warning("Some approved cohort videos are missing from this snapshot.")
    else:
        st.warning("Approved 500-video cohort membership is unverified for this export.")
    provenance = manifest_provenance(manifest)
    st.caption("Loaded export: " + provenance["timestamp"]
               + " | contract: " + provenance["contract"]
               + " | source: " + provenance["source"])
    absent = missing_countries(manifest)
    totals = exported_counts(manifest)
    if totals:
        st.caption("Exported records per country: "
                   + " · ".join(f"{iso.upper()} {count:,}" for iso, count in totals.items())
                   + f" · total {sum(totals.values()):,}")
    if absent:
        st.warning("Countries not represented by this export: " + ", ".join(absent)
                   + ". No missing records are inferred.")
else:
    st.warning("Export provenance manifest missing. Data freshness and completeness are unverified.")
if frame.empty:
    st.info("No local EP24 export found. Provide a private combined.csv, records.jsonl or SQLite database. No records are fabricated.")
    st.stop()

if "country" in frame:
    totals = frame["country"].fillna("unknown").astype(str).value_counts()
    st.sidebar.markdown("### Corpus")
    st.sidebar.caption(f"{int(totals.sum())} records in this export")
    scopes = ["All countries"] + [f"{name} ({count})" for name, count in totals.items()]
    scope = st.sidebar.radio("Country scope", scopes)
    if scope != "All countries":
        picked = scope.rsplit(" (", 1)[0]
        frame = frame[frame["country"].fillna("unknown").astype(str) == picked]

for column, label in (("country", "Country"), ("source_type", "Platform"),
                      ("source_language", "Language"), ("language", "Source language"),
                      ("laclau_status", "Discourse status")):
    if column in frame:
        options = sorted(frame[column].dropna().astype(str).unique().tolist())
        selected = st.sidebar.multiselect(label, options)
        if selected:
            frame = frame[frame[column].astype(str).isin(selected)]
if "video_id" in frame:
    query = st.sidebar.text_input("Video ID contains")
    if query:
        frame = frame[frame["video_id"].astype(str).str.contains(query, case=False, regex=False)]
date_field = next((key for key in ("created_at", "published_at", "source_recording")
                   if key in frame.columns), None)
if date_field is not None:
    dates = pd.to_datetime(frame[date_field], errors="coerce", utc=True)
    valid_dates = dates.dropna()
    if not valid_dates.empty:
        beginning, ending = valid_dates.min().date(), valid_dates.max().date()
        picked = st.sidebar.date_input("Publication / recording date", value=(beginning, ending),
                                        min_value=beginning, max_value=ending)
        if isinstance(picked, (tuple, list)) and len(picked) == 2:
            frame = frame.loc[dates.dt.date.between(picked[0], picked[1])]
view = st.sidebar.radio("Research view", [
    "Corpus overview", "Video browser", "Pipeline overview", "Multimodal · Steps 0–5",
    "Laclaudian discourse · Step 6", "DNA · Step 7",
    "Social network · Step 8", "Combined multilayer", "RDF · Step 9",
    "Legacy parity · workbench", "Legacy / QA", "Data & methods",
])
data = rows(frame)
st.caption(f"{len(data)} records match current filters. All graph views are bounded and evidence-linked.")
st.download_button("Download filtered video table (CSV)", data=researcher_csv(frame),
                   file_name="ep24_filtered_videos.csv", mime="text/csv",
                   help="Contains the current filtered research data; only download to an approved location.")

def table(items, key):
    """A table whose selected row becomes the inspected record (drilldown to source)."""
    if not items:
        st.info("No exported evidence available for this view.")
        return
    event = st.dataframe(pd.DataFrame([{k.replace("_", " ").capitalize(): readable(v)
                                        for k, v in item.items()
                                        if k in {"document", "step", "stage", "status", "records",
                                                 "source", "target", "type", "label", "country",
                                                 "actor", "actor_name_raw", "concept", "concept_name_raw",
                                                 "stance", "position", "evidence", "evidence_quote",
                                                 "relation_type", "quote", "confidence", "uncertainty",
                                                 "Concepts and evidence", "abstention", "read", "exported", "duplicates",
                                                 "invalid_ids", "processing_status", "processing_reason", "quality"}}
                                       for item in items]), use_container_width=True,
                         on_select="rerun", selection_mode="single-row", key=key)
    chosen = getattr(event, "selection", None)
    rows_selected = list(getattr(chosen, "rows", []) or [])
    if rows_selected:
        document = (items[rows_selected[0]] or {}).get("document")
        if document:
            st.session_state["ep24_inspect"] = document
            st.caption(f"Selected `{document}` — the inspector below follows the selection.")

def pick_record():
    names = [(identity(row), row) for row in data if identity(row)]
    if not names:
        st.warning("No records with stable source identities")
        return None
    labels = [f"{i+1}: {text(row.get('title')) or 'Untitled video'} · "
              f"{text(row.get('country'))} · {text(row.get('source_type'))}"
              for i, (_, row) in enumerate(names)]
    wanted = st.session_state.get("ep24_inspect")
    default = next((i for i, (name, _) in enumerate(names) if name == wanted), 0)
    selected = st.selectbox("Inspect source record", range(len(labels)), index=default,
                            format_func=lambda i: labels[i])
    st.session_state["ep24_inspect"] = names[selected][0]
    return names[selected][1]

def inspect(row):
    render_inspector(root, row)
    # Technical material is a separate opt-in operator surface, disabled by default.
    if (row and os.environ.get("LACLAUGPT_VIS_EP24_DIAGNOSTICS") == "1"
            and st.checkbox("Show Diagnostics / Provenance")):
        st.json({k: unpack(v) for k, v in row.items()})


def evidence_rows(field, inner):
    output = []
    for row in data:
        value = unpack(row.get(field))
        if isinstance(value, dict):
            value = value.get(inner, [])
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    output.append({"document": identity(row), **item})
    return output

if view == "Corpus overview":
    render_overview(frame, corpus_total)
    inspect(pick_record())
elif view == "Video browser":
    render_browser(frame)
    inspect(pick_record())
elif view == "Pipeline overview":
    st.subheader("Step-by-step observability")
    summary = []
    for step, (label, _) in STAGES.items():
        counts = pd.Series([status(row, step, rdf_available=bool(rdf_files(root)))
                            for row in data]).value_counts()
        for s, count in counts.items():
            summary.append({"step": step, "stage": label, "status": s, "records": int(count)})
    table(summary, "status_table")
    if "country" in frame:
        st.bar_chart(frame["country"].fillna("unknown").value_counts())
    inspect(pick_record())
elif view == "Multimodal · Steps 0–5":
    columns = [k for k in ("country", "video_id", "source_type", "asr_transcript",
               "ocr_1", "frame_analysis_1", "vllm_video_analysis",
               "summary_analysis", "postprocess_entities", "postprocess_themes")
               if k in frame]
    render_browser(frame)
    inspect(pick_record())
elif view == "Laclaudian discourse · Step 6":
    st.warning("Candidate interpretations require researcher review; counts never prove hegemony.")
    table([{"document": identity(row), "status": status(row, 6),
           "Concepts and evidence": readable(row.get("laclau_structured_json")),
           "abstention": text(row.get("laclau_abstention_reason"))} for row in data
           if status(row, 6) != "unavailable"], "laclau_table")
    inspect(pick_record())
elif view == "DNA · Step 7":
    st.caption("Actor–concept positions only, never empirical actor–actor social ties.")
    evidence = dna_evidence(data, root)
    if evidence.counts.get("read"):
        counts = evidence.counts
        st.caption(f"DNA child records: {counts['read']} read, {counts['matched']} matched to "
                   f"filtered source videos; {counts['orphan']} orphan, {counts['ambiguous']} "
                   f"ambiguous, {counts['duplicate']} duplicate.")
        if counts["orphan"] or counts["ambiguous"]:
            st.warning("Some child statements cannot be safely linked to a source video. "
                       "They have been excluded; check the producer's ingest-to-video mapping.")
    if evidence.statements:
        st.caption(f"{evidence.statements} statements from {evidence.records} records "
                   f"(read from the export's {evidence.source}).")
    else:
        st.info("No DNA statements in the export for this selection. "
                "This may indicate an incomplete upstream stage.")
    from laclaugpt_visualization.researcher_views import dna_network_figure
    figure = dna_network_figure(list(evidence.items))
    if figure is not None:
        st.plotly_chart(figure, use_container_width=True)
        st.caption("Bounded actor–concept projection. Positions and quotations are in the statement table.")
    table(list(evidence.items)[:2500], "dna_table")
    inspect(pick_record())
elif view == "Social network · Step 8":
    st.caption("Only edges provided with source, target, type and evidence can count as SNA ties.")
    edges = evidence_rows("sna_edges_json", "edges")
    edges = [e for e in edges if e.get("evidence_quote") and e.get("relation_type")
             and e.get("source") and e.get("target")]
    if edges:
        import networkx as nx
        import plotly.graph_objects as go
        network = nx.DiGraph()
        for edge in edges[:300]:
            network.add_edge(str(edge["source"]), str(edge["target"]))
        positions = nx.spring_layout(network, seed=17)
        figure = go.Figure()
        for edge in edges[:300]:
            a, b = positions[str(edge["source"])], positions[str(edge["target"])]
            figure.add_trace(go.Scatter(x=[a[0], b[0]], y=[a[1], b[1]], mode="lines",
                                       text=[readable(edge)] * 2, hoverinfo="text", showlegend=False))
        figure.add_trace(go.Scatter(x=[positions[n][0] for n in network],
                                   y=[positions[n][1] for n in network], mode="markers+text",
                                   text=list(network), showlegend=False))
        figure.update_layout(height=450, xaxis={"visible": False}, yaxis={"visible": False})
        st.plotly_chart(figure, use_container_width=True)
        st.caption("At most 300 exported evidenced ties. Direction/type and source videos remain "
                   "in the evidence table; layout is descriptive.")
    table(edges[:2500], "sna_table")
    inspect(pick_record())
elif view == "Combined multilayer":
    max_records = st.slider("Maximum records", 10, 1000, 250, 10)
    max_edges = st.slider("Maximum edges", 50, 2500, 500, 50)
    graph = multilayer(data, max_records=max_records, max_edges=max_edges)
    for warning in graph.warnings:
        st.warning(warning)
    st.write(f"{len(graph.nodes)} typed nodes and {len(graph.edges)} traceable edges")
    types = sorted({x["type"] for x in graph.edges})
    selected_types = st.multiselect("Visible edge types", types, default=types)
    visible = [x for x in graph.edges if x["type"] in selected_types]
    table(visible, "combined_edges")
    with st.expander("Node table"):
        table(list(graph.nodes), "combined_nodes")
    # Graph geometry is illustrative only. The edge table remains authoritative.
    if visible:
        import networkx as nx
        import plotly.graph_objects as go
        network = nx.Graph()
        for edge in visible[:500]:
            network.add_edge(edge["source"], edge["target"])
        positions = nx.spring_layout(network, seed=17)
        xx, yy = [], []
        for a, b in network.edges():
            xx += [positions[a][0], positions[b][0], None]
            yy += [positions[a][1], positions[b][1], None]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=xx, y=yy, mode="lines", line={"color": "#8b97a7", "width": 1}, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=[positions[n][0] for n in network],
                                 y=[positions[n][1] for n in network],
                                 mode="markers", text=list(network),
                                 hoverinfo="text", marker={"size": 8}))
        fig.update_layout(height=500, showlegend=False, xaxis={"visible": False},
                          yaxis={"visible": False})
        st.plotly_chart(fig, use_container_width=True)
    inspect(pick_record())
elif view == "RDF · Step 9":
    files = rdf_files(root)
    if not files:
        st.info("No graph.ttl or graph.nt exported. Step 9 cannot be marked complete.")
    for p in files:
        st.write({"file": str(p.relative_to(root)), "bytes": p.stat().st_size})
        with st.expander("Preview RDF (first 40 lines)"), \
                p.open(encoding="utf-8", errors="replace") as stream:
            st.code("".join([next(stream, "") for _ in range(40)]), language="turtle")
    inspect(pick_record())
elif view == "Legacy / QA":
    # The radio offered this view with no handler, so selecting it rendered a blank page. Its useful content
    # is the legacy comparison itself: which legacy columns this export can serve, which it cannot, and what
    # the export's own QA counters say (#263).
    st.subheader("Legacy comparison and export QA")
    st.caption("Which legacy :8501 columns this export can serve — the same facts as the parity matrix.")
    legacy_columns = {
        "whisper transcript": "asr_transcript",
        "whisper translation": "asr_translation",
        "OCR frame 1": "ocr_1",
        "frame analysis 1": "frame_analysis_1",
        "LLM summary": "summary_analysis",
        "formula of populism": "formula_of_populism_analysis",
        "political preference": "political_preference",
        "video duration": "video_duration_seconds",
        "sentiments": "positive",
        "recording date": "timestamp",
        "platform": "source_type",
        "researcher note": "researcher_note",
        "ManifestoBERTa class": "manifestoberta_predicted_class",
        "LDA topic": "lda_topic",
    }
    availability = [
        {
            "legacy field": legacy,
            "new column": column,
            "present": "yes" if column in frame.columns else "no",
            "filled": (f"{int(frame[column].notna().sum()):,}" if column in frame.columns else "—"),
        }
        for legacy, column in legacy_columns.items()
    ]
    st.dataframe(pd.DataFrame(availability), hide_index=True, use_container_width=True)
    absent = [row["legacy field"] for row in availability if row["present"] == "no"]
    if absent:
        st.warning("Not reproducible from this export: " + ", ".join(absent)
                   + ". See the parity matrix for the decision each one needs.")
    if manifest:
        qa = manifest.get("qa_counts") or {}
        if qa:
            st.markdown("**Exporter QA counters**")
            st.dataframe(pd.DataFrame([{"counter": key, "value": value} for key, value in qa.items()]),
                         hide_index=True, use_container_width=True)
        else:
            st.caption("The manifest carries no qa_counts.")
    else:
        st.info("No manifest next to the export, so export QA cannot be reported.")
elif view == "Legacy parity · workbench":
    # Parity with the legacy :8501 workbench (#263): the same filters, the same nine per-record tabs and
    # the same nine aggregate tabs, on the reprocessed export. Read-only on purpose — where a researcher's
    # decision lands is the open decision in #263 §4, and inventing a second write path would be worse than
    # one increment of a reader that cannot yet record a judgement.
    st.subheader("Legacy parity · researcher workbench")
    st.caption("Read-only. Review flags, cut/split and notes are not written here; see #263 §4.")
    children = load_children(root, frame)
    workbench = apply_filters(
        frame,
        countries=[str(scope.rsplit(" (", 1)[0])] if scope != "All countries" else [],
    )
    st.caption(f"{len(workbench):,} of {len(frame):,} records match the sidebar filters.")

    record_view, aggregate_view = st.tabs(["Records", "Corpus"])
    with record_view:
        if workbench.empty:
            st.info("No record matches the current filters.")
        else:
            labels = [f"{index + 1}. {str(value)[:90]}"
                      for index, value in enumerate(workbench.get("video_id", workbench.index))]
            chosen = st.selectbox("Record", labels, key="parity_record")
            row = workbench.iloc[labels.index(chosen)].to_dict()
            tabs = record_tabs(row, children)
            names = list(tabs)
            rendered = st.tabs(names)
            for tab, panel in zip(rendered, names):
                content_of = tabs[panel]
                with tab:
                    st.markdown(f"**{panel}**")
                    if not content_of["available"]:
                        st.warning(content_of["reason"] or "No source in the reprocessed export.")
                        continue
                    # Values are rendered as text, not markdown: these are corpus-derived strings, and a
                    # transcript that happens to contain markdown must not be interpreted by the page.
                    for block in content_of["blocks"]:
                        st.markdown(f"*{block['label']}*")
                        st.text(block["value"])
                    if content_of["note"]:
                        st.caption(content_of["note"])
                    if content_of["absent"]:
                        st.caption("Not carried by this export: " + ", ".join(content_of["absent"])
                                   + ". Unavailable is not the same as empty.")
                    if content_of["empty"]:
                        st.caption("No output for this record: " + ", ".join(content_of["empty"])
                                   + " — an absence of output, not a finding that the video has none.")

    with aggregate_view:
        # A count without its denominator and identity rule is not a claim (#205).
        st.caption(f"Denominator: {len(workbench):,} records in the filtered frame — one row per video, "
                   "identity `source_key`. Every figure below counts videos, not mentions.")
        legacy = st.columns(2)
        with legacy[0]:
            st.markdown("**Frequency**")
            st.dataframe(frequency_by(workbench), hide_index=True, use_container_width=True)
            st.dataframe(duration_by(workbench), hide_index=True, use_container_width=True)
        with legacy[1]:
            st.markdown("**Sentiments** (records with a non-zero score)")
            st.dataframe(sentiment_counts(workbench), hide_index=True, use_container_width=True)
            st.markdown("**Languages**")
            st.dataframe(language_counts(workbench), hide_index=True, use_container_width=True)

        st.markdown("**Entities** (top labels) and **Themes** — counted once per video")
        pair = st.columns(2)
        with pair[0]:
            st.dataframe(child_counts(children, "postprocess_entities"), hide_index=True,
                         use_container_width=True)
        with pair[1]:
            st.dataframe(child_counts(children, "postprocess_themes"), hide_index=True,
                         use_container_width=True)

        st.markdown("**Statistics** — records by country, preference and source type")
        st.dataframe(frequency_by(workbench, "country"), hide_index=True, use_container_width=True)
        st.dataframe(frequency_by(workbench, "source_type"), hide_index=True, use_container_width=True)

        over_time = st.tabs(["Themes over time", "Persons over time"])
        with over_time[0]:
            st.dataframe(child_counts_over_time(children, workbench, "postprocess_themes"),
                         hide_index=True, use_container_width=True)
        with over_time[1]:
            st.dataframe(child_counts_over_time(children, workbench, "postprocess_entities"),
                         hide_index=True, use_container_width=True)

    with st.expander("Parity matrix — every legacy tab, and why one is unavailable"):
        st.dataframe(parity_rows(), hide_index=True, use_container_width=True)
        missing = unsupported_tabs()
        if missing:
            st.caption("Unavailable in the reprocessed export: " + ", ".join(missing)
                       + " (see the matrix note for each).")
elif view == "Data & methods":
    st.subheader("Export manifest and stage coverage")
    if not manifest:
        st.info("No MANIFEST.json next to the export. Coverage cannot be asserted without it.")
    else:
        # Two real manifest shapes: the #210 Mongo refresh writes builder_version/generated_at, the
        # checkpoint exporter writes version/exported_at. Neither may render as "None" (#242).
        builder = manifest.get("builder_version") or manifest.get("version") or "unknown"
        generated = manifest.get("generated_at") or manifest.get("exported_at") or "unknown"
        st.caption(f"Builder `{builder}` · generated {generated} · schema {SCHEMA_VERSION}")
        table(manifest_counts_rows(manifest), "manifest_counts")
        covering = coverage_rows(manifest)
        if covering:
            st.markdown("**Stage coverage** — denominator is that country's exported records. "
                        "`not_exported` means the batch never produced that stage; it is not a "
                        "failure, and it is not a zero.")
            st.dataframe(pd.DataFrame(covering), use_container_width=True)
            errored = [row for row in covering if row.get("errored")]
            if errored:
                st.caption("Stages with errors: "
                           + ", ".join(f"{row['country']} step {row['stage']} "
                                       f"({row['errored']} errored)" for row in errored)
                           + " — those documents are still shown with what was produced.")
        inputs = manifest.get("inputs") or {}
        profiles = {k: (v or {}).get("profile", "reprocessed") for k, v in inputs.items()}
        st.markdown("**Source profile per country**")
        st.write(profiles)
        dropped = {k: (v or {}).get("dropped_reasons") or {} for k, v in inputs.items()}
        with st.expander("Dropped source columns and why"):
            for country, reasons in dropped.items():
                if reasons:
                    st.markdown(f"*{country}*")
                    st.dataframe(pd.DataFrame([{"column": c, "reason": r}
                                               for c, r in sorted(reasons.items())]),
                                 use_container_width=True)
        unaccounted = manifest.get("unaccounted_source_columns") or {}
        if any(unaccounted.values()):
            st.warning("Unclassified producer columns: " + json.dumps(unaccounted))
        failures = manifest.get("parse_failures") or {}
        if any(any(v.values()) for v in failures.values() if isinstance(v, dict)):
            st.warning("Unparseable JSON cells (excluded from child tables): " + json.dumps(failures))
        st.caption("A status field proves a stage ran. It does not validate the interpretation, "
                   "and a missing stage is never read as \"no phenomenon\".")
else:
    st.caption("Raw export QA and optional legacy comparison; nothing auto-corrected.")
    st.write({"duplicate_namespaced_ids":
              int(pd.Series([identity(row) for row in data if identity(row)]).duplicated().sum()),
              "missing_stable_ids": sum(not identity(row) for row in data)})
    table([{"document": identity(row), "processing_status": row.get("processing_status"),
            "processing_reason": row.get("processing_status_reason"),
            "quality": row.get("summary_quality_status")} for row in data], "qa_table")
    inspect(pick_record())
