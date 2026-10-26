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
    from laclaugpt_visualization.ep24_reprocessed import (
        SCHEMA_VERSION,
        STAGES,
        coverage_rows,
        identity,
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
    from ep24_reprocessed import (  # type: ignore[no-redef]
        SCHEMA_VERSION,
        STAGES,
        coverage_rows,
        identity,
        multilayer,
        rdf_files,
        read_manifest,
        read_records,
        rows,
        status,
        text,
        unpack,
    )

st.set_page_config(page_title="EP24 Reprocessed", layout="wide")
st.title("EP24 Reprocessed · research explorer")
st.caption("Read-only multimodal pipeline evidence | Separate from AI26 | " + SCHEMA_VERSION)
root = st.sidebar.text_input("Private EP24 exported data root",
                             value=os.environ.get("LACLAUGPT_VIS_ANALYSIS_DATA_DIR", "data"))
frame = read_records(root)
manifest = read_manifest(root)
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
                      ("source_language", "Language"), ("laclau_status", "Discourse status")):
    if column in frame:
        options = sorted(frame[column].dropna().astype(str).unique().tolist())
        selected = st.sidebar.multiselect(label, options)
        if selected:
            frame = frame[frame[column].astype(str).isin(selected)]
if "video_id" in frame:
    query = st.sidebar.text_input("Video ID contains")
    if query:
        frame = frame[frame["video_id"].astype(str).str.contains(query, case=False, regex=False)]
view = st.sidebar.radio("Research view", [
    "Pipeline overview", "Multimodal · Steps 0–5",
    "Laclaudian discourse · Step 6", "DNA · Step 7",
    "Social network · Step 8", "Combined multilayer", "RDF · Step 9",
    "Legacy / QA", "Data & methods",
])
data = rows(frame)
st.caption(f"{len(data)} records match current filters. All graph views are bounded and evidence-linked.")

def table(items, key):
    """A table whose selected row becomes the inspected record (drilldown to source)."""
    if not items:
        st.info("No exported evidence available for this view.")
        return
    event = st.dataframe(pd.DataFrame(items), use_container_width=True,
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
    labels = [f"{i+1}: {name}" for i, (name, _) in enumerate(names)]
    wanted = st.session_state.get("ep24_inspect")
    default = next((i for i, (name, _) in enumerate(names) if name == wanted), 0)
    selected = st.selectbox("Inspect source record", range(len(labels)), index=default,
                            format_func=lambda i: labels[i])
    st.session_state["ep24_inspect"] = names[selected][0]
    return names[selected][1]

def inspect(row):
    if not row:
        return
    st.subheader("Evidence inspector")
    st.caption("All values are verbatim exported fields. Missing means unavailable, not negative evidence.")
    st.write({"document_identity": identity(row), "country": row.get("country"),
              "video_id": row.get("video_id"), "storage_id": row.get("_storage_id"),
              "source_platform": row.get("source_type")})
    for step, (label, keys) in STAGES.items():
        with st.expander(f"Step {step} · {label} · {status(row, step, rdf_available=bool(rdf_files(root)))}"):
            values = {k: unpack(row[k]) for k in keys if k in row and text(row.get(k))}
            # Keep every extra per-stage provenance key inspectable.
            prefixes = {1: ("asr_", "ocr_", "preprocess_"), 2: ("frame_analysis_",),
                        3: ("vllm_video_",), 4: ("summary_",),
                        5: ("postprocess_", "ep24_"), 6: ("laclau_", "formula_of_populism_"),
                        7: ("dna_",), 8: ("sna_",)}
            for key in row:
                if (key not in values
                        and any(key.startswith(prefix) for prefix in prefixes.get(step, ()))
                        and text(row.get(key))):
                    values[key] = unpack(row[key])
            st.json(values if values else {"availability": "not exported"})
    with st.expander("Complete source/export row"):
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

if view == "Pipeline overview":
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
    st.dataframe(frame[columns].head(1000), use_container_width=True)
    inspect(pick_record())
elif view == "Laclaudian discourse · Step 6":
    st.warning("Candidate interpretations require researcher review; counts never prove hegemony.")
    table([{"document": identity(row), "status": status(row, 6),
           "structured": text(row.get("laclau_structured_json")),
           "abstention": text(row.get("laclau_abstention_reason"))} for row in data
           if status(row, 6) != "unavailable"], "laclau_table")
    inspect(pick_record())
elif view == "DNA · Step 7":
    st.caption("Actor–concept positions only, never empirical actor–actor social ties.")
    table(evidence_rows("dna_statements_json", "statements")[:2500], "dna_table")
    inspect(pick_record())
elif view == "Social network · Step 8":
    st.caption("Only edges provided with source, target, type and evidence can count as SNA ties.")
    edges = evidence_rows("sna_edges_json", "edges")
    edges = [e for e in edges if e.get("evidence_quote") and e.get("relation_type")]
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
elif view == "Data & methods":
    st.subheader("Export manifest and stage coverage")
    if not manifest:
        st.info("No MANIFEST.json next to the export. Coverage cannot be asserted without it.")
    else:
        st.caption(f"Builder `{manifest.get('builder_version')}` · generated "
                   f"{manifest.get('generated_at')} · schema {SCHEMA_VERSION}")
        counts = manifest.get("record_counts") or {}
        rows_counts = [{"country": k, **v} for k, v in counts.items() if isinstance(v, dict)]
        table(rows_counts, "manifest_counts")
        covering = coverage_rows(manifest)
        if covering:
            st.markdown("**Stage coverage** — denominator is that country's exported records.")
            st.dataframe(pd.DataFrame(covering), use_container_width=True)
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
