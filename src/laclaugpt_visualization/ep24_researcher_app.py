"""FI/PL/PT Monday500 human-research dashboard. No debug columns or raw row dumps.

Launch: streamlit run src/laclaugpt_visualization/ep24_researcher_app.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from laclaugpt_visualization.demo_auth import require_demo_password
from laclaugpt_visualization.ep24_reprocessed import (
    STAGES,
    dna_evidence,
    identity,
    multilayer,
    rdf_files,
    read_manifest,
    read_records,
    rows,
    status,
    unpack,
)
from laclaugpt_visualization.ep24_researcher import (
    COUNTRIES,
    DNA_FIELDS,
    SNA_FIELDS,
    cohort_warnings,
    coverage,
    evidence_sections,
    friendly,
    research_children,
    view,
)

st.set_page_config(page_title="EP2024 · FI/PL/PT research", layout="wide")
if not os.environ.get("LACLAUGPT_VIS_DEMO_PASSWORD"):
    st.error("Research access not configured. Configure the server-local password.")
    st.stop()
require_demo_password()
palette = ["#6C63FF", "#00C2A8", "#FF6B8A", "#FFA94D", "#4DABF7",
           "#B197FC", "#63E6BE", "#F783AC", "#FFD43B", "#74C0FC"]
legacy_theme = go.layout.Template()
legacy_theme.layout = go.Layout(colorway=palette, paper_bgcolor="#FFFFFF",
    plot_bgcolor="#FAFBFF", font={"family": "Inter, Segoe UI, sans-serif",
    "size": 13, "color": "#0F172A"})
pio.templates["ep2024_groovy"] = legacy_theme
pio.templates.default = "ep2024_groovy"
st.title("EP2024 · Finland, Poland & Portugal")
st.caption("LaclauGPT multimodal research explorer | 500-video test cohorts | "
           "Interpretations are model outputs, not validated findings")
root = Path(os.environ.get("LACLAUGPT_VIS_ANALYSIS_DATA_DIR", "data"))
frame = read_records(root)
manifest = read_manifest(root)
if frame.empty:
    st.error("No private export loaded. Configure LACLAUGPT_VIS_ANALYSIS_DATA_DIR.")
    st.stop()

warnings = cohort_warnings(frame, manifest)
for warning in warnings:
    st.warning(warning)
if not warnings:
    st.success("All three 500-video cohorts and the dataset identifier match the export.")
else:
    st.error("Invalid or incomplete Monday500 cohort. Mount a verified, approved snapshot.")
    st.stop()
if manifest:
    st.caption(f"Snapshot: {manifest.get('generated_at', 'not specified')} | "
               f"exporter: {manifest.get('builder_version', 'not specified')}")
else:
    st.warning("No provenance manifest. Treat this data as unverified.")

# The research dashboard only reads; never modifies or exports raw pipeline records.
country_col = frame.get("country", pd.Series([""] * len(frame), index=frame.index))
normalized_country = country_col.fillna("").astype(str).str.lower().map(COUNTRIES)
chosen = st.sidebar.selectbox("Country", ["All countries", "Finland", "Poland", "Portugal"])
if chosen != "All countries":
    frame = frame.loc[normalized_country == chosen].copy()
for key, title in (("source_type", "Platform"), ("source_language", "Language")):
    if key in frame:
        values = sorted(frame[key].dropna().astype(str).unique())
        selection = st.sidebar.multiselect(title, values)
        if selection:
            frame = frame[frame[key].astype(str).isin(selection)]
search = st.sidebar.text_input("Search video, caption or summary")
if search:
    allowed = [key for key in ("video_id", "caption", "source_caption",
                               "summary_analysis", "postprocess_summary_md") if key in frame]
    if allowed:
        mask = pd.Series(False, index=frame.index)
        for key in allowed:
            mask |= frame[key].fillna("").astype(str).str.contains(search, case=False, regex=False)
        frame = frame.loc[mask]
if "published_at" in frame or "created_at" in frame:
    key = "published_at" if "published_at" in frame else "created_at"
    times = pd.to_datetime(frame[key], errors="coerce", utc=True)
    valid = times.dropna()
    if len(valid):
        dates = st.sidebar.date_input("Publication dates",
                                     (valid.min().date(), valid.max().date()),
                                     min_value=valid.min().date(), max_value=valid.max().date())
        if isinstance(dates, (tuple, list)) and len(dates) == 2:
            frame = frame.loc[times.dt.date.between(*dates)]

data = rows(frame)
st.metric("Videos matching filters", f"{len(frame):,}")
st.caption("Counts use filtered exported rows. Missing stage evidence is not a negative finding.")
tabs = st.tabs(["Overview", "Videos & multimodal evidence", "Entities and themes",
                "Laclau discourse", "DNA", "SNA", "Multilayer", "RDF & methods"])

def table(df: pd.DataFrame, name: str):
    if df.empty:
        st.info(f"No recorded evidence for {name} in this selection.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

def list_terms(key: str):
    from collections import Counter
    counts = Counter()
    for row in data:
        value = unpack(row.get(key))
        if isinstance(value, dict):
            value = next((v for v in value.values() if isinstance(v, list)), [])
        if not isinstance(value, list):
            continue
        for entry in value:
            term = (entry.get("canonical_name") or entry.get("name") or entry.get("label")
                    if isinstance(entry, dict) else entry)
            if term:
                counts[str(term)] += 1
    return pd.DataFrame([{"Term": term, "Videos / mentions": n}
                         for term, n in counts.most_common(25)])

with tabs[0]:
    st.subheader("Corpus and pipeline coverage")
    if "country" in frame:
        countries = frame.country.fillna("Unknown").astype(str).map(
            lambda c: COUNTRIES.get(c.lower(), c))
        st.plotly_chart(px.bar(countries.value_counts().rename_axis("Country")
                               .reset_index(name="Videos"),
                               x="Country", y="Videos", color="Country",
                               title="Videos by country"), use_container_width=True)
    if "source_type" in frame:
        platform = frame.source_type.fillna("Unknown").value_counts().rename_axis(
            "Platform").reset_index(name="Videos")
        st.plotly_chart(px.bar(platform, x="Platform", y="Videos",
                               title="Videos by platform"), use_container_width=True)
    for key in ("published_at", "created_at"):
        if key in frame:
            dates = pd.to_datetime(frame[key], utc=True, errors="coerce").dt.date.dropna()
            if not dates.empty:
                byday = dates.value_counts().sort_index().rename_axis("Date").reset_index(name="Videos")
                st.plotly_chart(px.line(byday, x="Date", y="Videos",
                                        title="Publication timeline"), use_container_width=True)
            break
    table(coverage(frame), "stage coverage")

with tabs[1]:
    st.subheader("Searchable video catalogue")
    shown = view(frame)
    table(shown, "videos")
    st.download_button("Download researcher-readable filtered CSV",
                       data=shown.to_csv(index=False).encode("utf-8-sig"),
                       file_name="ep24_research_videos.csv", mime="text/csv")
    if data:
        options = [f"{i+1}. {row.get('country', '')} · {row.get('video_id', 'unknown')}"
                   for i, row in enumerate(data)]
        selected = st.selectbox("Inspect a video", range(len(data)),
                                format_func=lambda i: options[i])
        row = data[selected]
        st.caption(f"Source: {friendly(row.get('source_url')) or 'No source link exported'}")
        for heading, value in evidence_sections(row):
            with st.expander(heading, expanded=heading in (
                "Multimodal summary", "Research summary", "Transcript")):
                st.write(value)
        st.markdown("**Pipeline availability**")
        table(pd.DataFrame([{"Step": step, "Analysis": label,
                             "Status": status(row, step)}
                            for step, (label, _) in STAGES.items()]), "stage status")

with tabs[2]:
    for key, label in (("postprocess_entities", "Entities"),
                       ("postprocess_themes", "Themes")):
        st.subheader(label)
        terms = list_terms(key)
        if not terms.empty:
            st.plotly_chart(px.bar(terms.head(20), x="Videos / mentions", y="Term",
                                   orientation="h", title=label),
                            use_container_width=True)
        table(terms, label)
    st.caption("Entity and theme counts describe exported model labels, not independently verified facts.")

with tabs[3]:
    st.subheader("Laclaudian discourse")
    st.caption("Model-coded candidate signifiers, demands and antagonisms require researcher review.")
    discourse = []
    for record in data:
        if record.get("laclau_summary_md") or record.get("laclau_structured_json"):
            discourse.append({"Video": friendly(record.get("video_id")),
                              "Country": friendly(record.get("country")),
                              "Model interpretation": friendly(record.get("laclau_summary_md")),
                              "Structured coding": friendly(record.get("laclau_structured_json")),
                              "Status": status(record, 6)})
    table(pd.DataFrame(discourse), "discourse")

with tabs[4]:
    st.subheader("Discourse Network Analysis · actor–concept positions")
    evidence = dna_evidence(data, root)
    st.caption(f"{len(evidence.items)} evidenced statements, from {evidence.source}. "
               "Actor–concept relations are not actor–actor social ties.")
    dna = research_children(list(evidence.items)[:3000], DNA_FIELDS)
    table(dna, "DNA statements")
    if not dna.empty and "Actor" in dna and "Concept" in dna:
        pairs = dna[(dna["Actor"] != "") & (dna["Concept"] != "")]
        if not pairs.empty:
            popular = pairs.groupby(["Actor", "Concept"]).size().nlargest(50).reset_index(name="Statements")
            st.plotly_chart(px.scatter(popular, x="Actor", y="Concept", size="Statements",
                                       title="Actor–concept positions (statement counts)"),
                            use_container_width=True)

with tabs[5]:
    st.subheader("Social Network Analysis · evidenced actor–actor ties")
    ties = []
    for record in data:
        parsed = unpack(record.get("sna_edges_json"))
        if isinstance(parsed, dict):
            parsed = parsed.get("edges", [])
        for edge in parsed if isinstance(parsed, list) else []:
            if isinstance(edge, dict) and edge.get("evidence_quote") and edge.get("relation_type"):
                ties.append({"document": identity(record), **edge})
    table(research_children(ties[:3000], SNA_FIELDS), "evidenced SNA ties")
    if ties:
        import networkx as nx
        network = nx.DiGraph()
        for edge in ties[:250]:
            source = edge.get("source_actor") or edge.get("source_actor_id")
            target = edge.get("target_actor") or edge.get("target_actor_id")
            if source and target:
                network.add_edge(str(source), str(target))
        if network.number_of_edges():
            positions = nx.spring_layout(network, seed=24)
            xx, yy = [], []
            for a, b in network.edges():
                xx += [positions[a][0], positions[b][0], None]
                yy += [positions[a][1], positions[b][1], None]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=xx, y=yy, mode="lines",
                line={"color": "#8b97a7"}, hoverinfo="skip"))
            fig.add_trace(go.Scatter(
                x=[positions[n][0] for n in network],
                y=[positions[n][1] for n in network], text=list(network),
                mode="markers", hoverinfo="text", marker={"size": 10}))
            fig.update_layout(height=560, showlegend=False,
                xaxis={"visible": False}, yaxis={"visible": False})
            st.plotly_chart(fig, use_container_width=True)
    st.caption("Only upstream relationships carrying an evidence quotation and type appear here.")

with tabs[6]:
    st.subheader("Linked evidence layers")
    graph = multilayer(data, max_records=250, max_edges=1500)
    for warning in graph.warnings:
        st.warning(warning)
    st.caption("Connections are typed. Extracted concepts and DNA positions are not social ties.")
    edges = research_children(list(graph.edges), {
        "type": "Relationship type", "document": "Source video",
        "evidence": "Supporting evidence", "field": "Originating analysis"})
    table(edges, "multilayer evidence")
    counts = pd.DataFrame(graph.nodes)
    if not counts.empty:
        st.plotly_chart(px.bar(counts.type.value_counts().rename_axis("Node type")
                               .reset_index(name="Nodes"), x="Node type", y="Nodes",
                               title="Research graph node types"), use_container_width=True)

with tabs[7]:
    st.subheader("RDF and provenance")
    rdf = rdf_files(root)
    if rdf:
        st.caption("Available RDF artifacts: " + ", ".join(p.name for p in rdf))
    else:
        st.info("No RDF graph file in the selected export.")
    st.markdown("**Methods:** one exported video record per country-scoped identity; "
                "LLM-generated interpretation is not researcher validation. "
                "A stage with no output is not interpreted as a negative result.")
    if manifest:
        table(pd.DataFrame([{"Metadata": k, "Value": friendly(v)}
                            for k, v in manifest.items()
                            if k in {"generated_at", "dataset", "dataset_id",
                                     "builder_version", "schema", "contract"}]), "manifest")
    st.caption("Technical paths, record hashes, raw prompts and pipeline internals "
               "are intentionally absent from the researcher interface.")
