"""FI/PL/PT live steps 1–7 research explorer.

Launch:
    LACLAUGPT_VIS_LIVE_STEPS_DATA=<artifact dir> \
        streamlit run src/laclaugpt_visualization/live_steps_app.py

The artifacts come from ``tools/build_live_steps_artifacts.py``. This app reads them only: an index
row per video, a gzipped text bundle for the long cells, and the manifest that says which source
columns were dropped and why. A missing stage renders as *unavailable in this source*, never as 0.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from laclaugpt_visualization.live_steps import (
        STEPS,
        actor_comention_graph,
        affect_rows,
        bundle_text,
        child_records,
        clean,
        filter_records,
        laclau_summary,
        load,
        monthly_by,
        node_degrees,
        problem_rows,
        search_bundle,
        sentiment_totals,
        stage_availability,
        statement_spread,
        statement_table,
        status_counts,
        step_table,
        value_counts,
    )
except ModuleNotFoundError:  # standalone deployment: only this module and its helper were shipped
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from live_steps import (  # type: ignore[no-redef]
        STEPS,
        actor_comention_graph,
        affect_rows,
        bundle_text,
        child_records,
        clean,
        filter_records,
        laclau_summary,
        load,
        monthly_by,
        node_degrees,
        problem_rows,
        search_bundle,
        sentiment_totals,
        stage_availability,
        statement_spread,
        statement_table,
        status_counts,
        step_table,
        value_counts,
    )

from laclaugpt_visualization.researcher_views import render_stage_explorer

ROOT = (os.environ.get("LACLAUGPT_VIS_LIVE_STEPS_DATA")
        or os.environ.get("LACLAUGPT_VIS_ANALYSIS_DATA_DIR") or "data")

SEARCH_FIELDS = ("asr_transcript", "asr_translated", "ocr_1", "frame_analysis_1",
                 "vllm_video_analysis", "summary_analysis", "laclau_summary_md",
                 "dna_analysis_markdown", "sna_report_markdown")

try:
    from laclaugpt_visualization.demo_auth import require_demo_password
except ModuleNotFoundError:  # standalone deployment
    from demo_auth import require_demo_password  # type: ignore[no-redef]

st.set_page_config(page_title="NoöPunk · FI/PL/PT live steps 1–7", layout="wide")
# Security gate (#62): if LACLAUGPT_VIS_DEMO_PASSWORD is set, stop before loading the corpus.
require_demo_password()

frame, manifest = load(ROOT)
if frame.empty:
    st.title("FI/PL/PT live steps 1–7")
    st.info("No export found at this data root. Point LACLAUGPT_VIS_LIVE_STEPS_DATA at the artifact "
            "directory built by tools/build_live_steps_artifacts.py. No records are fabricated.")
    st.stop()

st.title("FI/PL/PT live pipeline · steps 1–7")
st.caption("Read-only multimodal evidence · Finland, Poland, Portugal · every long value is verbatim "
           "from the producer export")


@st.cache_data(show_spinner=False)
def step_structure(data_root: str, record_ids: tuple[str, ...]) -> tuple[dict, list[dict]]:
    """Step-6 structure for these records, read from the bundle once per selection."""
    bundle = bundle_text(data_root, ("laclau_structured_json",))
    rows = [{"record_id": record_id,
             "laclau_structured_json": (bundle.get(record_id) or {}).get("laclau_structured_json", "")}
            for record_id in record_ids]
    return laclau_summary(rows), affect_rows(rows)


@st.cache_data(show_spinner=False)
def hits(data_root: str, record_ids: tuple[str, ...], query: str) -> list[dict]:
    bundle = {record_id: payload for record_id, payload in
              bundle_text(data_root, SEARCH_FIELDS).items() if record_id in set(record_ids)}
    return search_bundle(bundle, query, SEARCH_FIELDS)


def chart(series: pd.Series, title: str, x: str = "records"):
    if series is None or len(series) == 0:
        st.info(f"No data for: {title}")
        return
    data = series.rename(x).reset_index()
    data.columns = ["value" if column == "index" else column for column in data.columns]
    st.plotly_chart(px.bar(data, x=x, y=data.columns[0], title=title), width='stretch')


def network_figure(nodes: pd.DataFrame, edges: pd.DataFrame, title: str,
                   node_weight: str = "statements", edge_weight: str = "videos"):
    """Force-directed actor–concept graph. Nodes are the producer's labels, never identifiers."""
    if nodes.empty or edges.empty:
        return None
    graph = nx.Graph()
    for row in nodes.itertuples():
        graph.add_node(row.id, label=row.label, kind=row.kind,
                       weight=getattr(row, node_weight, 1))
    for row in edges.itertuples():
        graph.add_edge(row.source, row.target, weight=getattr(row, edge_weight, 1),
                       stance=getattr(row, "stance", "co-mentioned"))
    position = nx.spring_layout(graph, seed=7, k=0.9, iterations=120)
    segments = []
    for source, target in graph.edges():
        segments.append((position[source][0], position[source][1], position[target][0],
                         position[target][1], graph.edges[source, target]["stance"]))
    axis = {"showgrid": False, "zeroline": False, "showticklabels": False}
    figure = go.Figure()
    for stance in sorted({segment[4] for segment in segments}):
        chosen = [segment for segment in segments if segment[4] == stance]
        xs, ys = [], []
        for x0, y0, x1, y1, _ in chosen:
            xs += [x0, x1, None]
            ys += [y0, y1, None]
        figure.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line={"width": 1.2, "color": "#b6bac0"},
                                    hoverinfo="skip", name=stance, legendgroup=stance))
    for kind, colour, size in (("actor", "#2f6f9f", 12), ("concept", "#e07b39", 10)):
        group = nodes[nodes["kind"] == kind]
        figure.add_trace(go.Scatter(
            x=[position[node][0] for node in group["id"]], y=[position[node][1] for node in group["id"]],
            mode="markers+text", name=kind, text=group["label"], textposition="top center",
            textfont={"size": 9},
            marker={"size": [size + 4 * float(value) ** 0.5 for value in group[node_weight]],
                    "color": colour, "opacity": 0.85,
                    "line": {"width": 1, "color": "#ffffff"}},
            hovertemplate="%{text}<extra>" + kind + "</extra>"))
    figure.update_layout(title=title, showlegend=True, height=560, xaxis=axis, yaxis=axis)
    return figure


def counts_of(frame: pd.DataFrame, column: str, limit: int = 15) -> pd.Series:
    """Value counts of an optional producer column: absent means no chart, never a KeyError."""
    if column not in frame.columns:
        return pd.Series(dtype=int)
    return frame[column].replace("", "not reported").value_counts().head(limit)


def table(rows: list[dict], key: str, caption: str = ""):
    """A dataframe whose selected row opens in the inspector."""
    if not rows:
        st.info("No exported evidence available for this view.")
        return
    display = pd.DataFrame(rows).astype(str).replace({"nan": "", "None": ""})
    if caption:
        st.caption(caption)
    event = st.dataframe(display, width='stretch', on_select="rerun",
                         selection_mode="single-row", key=key)
    selection = getattr(event, "selection", None)
    chosen = list(getattr(selection, "rows", []) or [])
    if chosen and "record_id" in display.columns:
        st.session_state["live_inspect"] = display.iloc[chosen[0]]["record_id"]


# -- sidebar: one filter path ------------------------------------------------------------------- #
st.sidebar.markdown("### Corpus")
st.sidebar.caption(f"{len(frame):,} videos in this export "
                   f"({', '.join(f'{k} {v}' for k, v in frame['country'].value_counts().items())})")
countries = st.sidebar.multiselect("Country", sorted(frame["country"].dropna().unique()))
platforms = st.sidebar.multiselect("Platform", sorted(frame["source_type"].dropna().unique()))
political = st.sidebar.multiselect("Political preference",
                                   sorted(frame["political_preference"].dropna().unique()))
months = st.sidebar.multiselect("Recording month", sorted(frame["month"].dropna().unique()))
min_steps = st.sidebar.slider("At least this many of steps 1–7 complete", 0, 7, 0)
query = st.sidebar.text_input("Video ID contains", key="live_video_query")
st.sidebar.caption("Recording month is derived from the media id (YYYYMMDD), not a producer field.")

filtered = filter_records(frame, countries=countries, platforms=platforms, political=political,
                          months=months, query=query, min_steps=min_steps)
st.caption(f"{len(filtered):,} of {len(frame):,} videos match the filters.")

tabs = st.tabs(["Overview", "Steps & coverage", "Search", "Record browser", "Discourse · DNA",
                "Network · SNA", "Problems", "Aggregates", "Data quality", "Methods", "Stage explorer"])

with tabs[0]:
    columns = st.columns(4)
    columns[0].metric("Videos", f"{len(filtered):,}")
    columns[1].metric("Countries", filtered["country"].nunique() if len(filtered) else 0)
    columns[2].metric("All 7 steps",
                      int((pd.to_numeric(filtered["pipeline_steps_ok"], errors="coerce") == 7).sum()))
    with_sna = (filtered["has_sna"].astype(str).str.lower().isin({"true", "1"})
                if "has_sna" in filtered else pd.Series(dtype=bool))
    columns[3].metric("With SNA", int(with_sna.sum()))
    left, right = st.columns(2)
    with left:
        chart(filtered["country"].value_counts(), "Videos by country")
        chart(filtered["political_preference"].value_counts(), "Videos by political preference")
        chart(filtered["asr_language"].value_counts(), "ASR language")
    with right:
        chart(filtered["source_type"].value_counts(), "Videos by platform")
        chart(pd.to_numeric(filtered["pipeline_steps_ok"], errors="coerce")
              .value_counts().sort_index(), "Steps 1–7 completed")
        durations = pd.to_numeric(filtered["duration_minutes"], errors="coerce").dropna()
        if len(durations):
            st.plotly_chart(px.histogram(durations.round(-1), nbins=30,
                                         title="Video duration (minutes, rounded to 10s)",
                                         labels={"value": "minutes"}),
                            width='stretch')
    spread = monthly_by(filtered, "source_type")
    if not spread.empty:
        st.plotly_chart(px.bar(spread, x="month", y="records", color="_split", barmode="stack",
                               title="Recording month by platform",
                               labels={"_split": "platform"}),
                        width='stretch')

with tabs[1]:
    st.subheader("Stage coverage")
    st.caption("Denominator is the exported records of that country. A stage the producer did not "
               "report is *unavailable*, not zero.")
    availability = stage_availability(manifest)
    if availability.empty:
        st.info("No stage coverage in the manifest.")
    else:
        st.dataframe(availability, width='stretch')
        st.plotly_chart(px.bar(availability, x="stage", y="pct", color="country", barmode="group",
                               title="Per-stage coverage (%)"), width='stretch')
    st.subheader("Step status per record")
    steps = step_table(filtered)
    if not steps.empty:
        st.dataframe(steps, width='stretch')
        st.plotly_chart(px.bar(steps, x="stage", y="pct", color="country", barmode="group",
                               title="Step completion in the current selection (%)"),
                        width='stretch')
    with st.expander("Status vocabulary as the producer wrote it"):
        for step, (label, _, _) in STEPS.items():
            column = f"step_0{step}_status"
            if column in filtered.columns:
                st.markdown(f"**Step {step} · {label}**")
                st.dataframe(status_counts(filtered, column), width='stretch')

with tabs[2]:
    st.subheader("Search the long cells")
    st.caption("Substring match over transcript, OCR, frame and video analysis, summary, Laclau and DNA "
               "text. Every hit is listed with a snippet; nothing is ranked.")
    needle = st.text_input("Search term", key="live_search",
                       placeholder="e.g. maahanmuutto, abortion, austerity")
    if needle:
        selected = tuple(clean(record_id) for record_id in filtered["record_id"])
        found = hits(ROOT, selected, needle)
        st.caption(f"{len(found)} field hits across {len({hit['record_id'] for hit in found})} videos.")
        if found:
            st.dataframe(pd.DataFrame(found), width='stretch')
            st.caption("Click a row to open the record in the browser tab.")
        else:
            st.info("No hit in the selected videos. That is a fact about this export, not about the "
                    "signifier in the world.")

with tabs[3]:
    st.subheader("Record browser")
    if filtered.empty:
        st.info("No records match the filters.")
    else:
        names = filtered[["record_id", "country", "video_id"]].astype(str)
        labels = [f"{row.country} · {row.video_id}" for row in names.itertuples()]
        wanted = st.session_state.get("live_inspect")
        default = next((index for index, label in enumerate(labels)
                        if wanted and wanted.endswith(clean(names.iloc[index]["video_id"]))), 0)
        picked = st.selectbox("Record", range(len(labels)), index=default,
                              format_func=lambda index: labels[index])
        row = filtered.iloc[picked]
        st.session_state["live_inspect"] = clean(row.get("record_id"))
        st.caption(f"{clean(row.get('record_id'))} · {clean(row.get('source_type'))} · "
                   f"{clean(row.get('political_preference'))} · "
                   f"{clean(row.get('duration_minutes'))} min · {clean(row.get('month'))}")

        long_fields = [field for _, (_, text_fields, _) in STEPS.items() for field in text_fields]
        bundle = bundle_text(ROOT, long_fields).get(clean(row.get("record_id")), {})
        st.markdown("**Producer metadata**")
        st.dataframe(pd.DataFrame([{key: clean(row.get(key)) for key in
                                    ("video_id", "_storage_id", "allas_filename", "source_recording",
                                     "sequence_number", "author_username", "account_type",
                                     "political_preference", "duration_minutes")}]),
                     width='stretch')
        available = [step for step, (_, text_fields, _) in STEPS.items()
                     if any(bundle.get(field) for field in text_fields)]
        st.markdown("**Steps**")
        status_strip = " · ".join(f"{step} {clean(row.get(f'step_0{step}_status')) or 'not reported'}"
                                  for step in range(1, 8))
        st.caption(status_strip + (f" · 8 {clean(row.get('sna_status')) or 'not reported'}"
                                   " (SNA: auxiliary, partial)"))
        if not available:
            st.info("No stage output in this record's bundle.")
        else:
            step = st.radio("Step", available, horizontal=True,
                            format_func=lambda index: f"{index} · {STEPS[index][0]}",
                            key="live_step_choice")
            label, text_fields, index_fields = STEPS[step]
            meta = {key: clean(row.get(key)) for key in index_fields if clean(row.get(key))}
            if meta:
                st.dataframe(pd.DataFrame([meta]), use_container_width=True)
            for field in text_fields:
                value = bundle.get(field)
                if not value:
                    st.caption(f"*{field}* — no output for this record in this stage.")
                    continue
                st.markdown(f"**{field}**")
                if isinstance(value, list):
                    st.caption(f"{len(value)} records")
                    st.dataframe(pd.DataFrame(value).astype(str), use_container_width=True)
                elif str(value).lstrip().startswith(("{", "[")):
                    st.code(str(value)[:20000], language="json")
                else:
                    st.write(str(value)[:20000])

with tabs[4]:
    st.subheader("Laclaudian discourse · step 6, and DNA · step 7")
    st.warning("Producer codes are candidate interpretations. Counts never prove hegemony, and a "
               "graph position is not evidence of guilt.")
    structure, affects = step_structure(ROOT, tuple(clean(record_id) for record_id in filtered["record_id"]))
    metrics = st.columns(5)
    metrics[0].metric("Records", structure["records"])
    metrics[1].metric("Min. conditions met", structure["conditions_met"],
                      help="formula_minimum_conditions_met, as the producer coded it")
    metrics[2].metric("With an articulated Us", structure["with_us"])
    metrics[3].metric("With a frontier", structure["with_frontier"])
    metrics[4].metric("With affects", structure["with_affects"])
    st.caption(f"{structure['affects']} affects · {structure['chains']} equivalence chains · "
               f"{structure['uncertainty_notes']} uncertainty notes · "
               f"{structure['with_counter_evidence']} records carry counter-evidence. "
               f"Two thirds of this corpus articulating no frontier is a finding, not a gap.")

    left, right = st.columns(2)
    with left:
        st.markdown("**Step 6 · producer status**")
        st.dataframe(status_counts(filtered, "laclau_status"), width='stretch')
        st.markdown("**Formula-of-populism conditions met**")
        st.dataframe(status_counts(filtered, "laclau_formula_conditions_met"), width='stretch')
        st.markdown("**Affects read from the text**")
        st.dataframe(structure["affect_labels"], width='stretch')
    with right:
        st.markdown("**Why the producer abstained**")
        if structure["abstentions"].empty:
            st.info("No abstention reasons in this selection.")
        else:
            st.dataframe(structure["abstentions"], width='stretch')
        st.markdown("**Step 7 · DNA status**")
        st.dataframe(status_counts(filtered, "dna_status"), width='stretch')

    st.markdown("**Affect spans**")
    table([{key: clean(item[key])[:220] for key in ("record_id", "country", "label",
                                                   "confidence", "text_span")}
           for item in affects], "affects_table",
          caption="Each affect points at the span it was read from; the label is the producer's.")

    statements = child_records(ROOT, filtered, "dna_statements_json")
    st.markdown("**Statements**")
    st.caption(f"{len(statements)} statements for this selection, read from the text bundle.")
    if statements:
        st.dataframe(statement_table(statements), width='stretch')
        statement_frame = pd.DataFrame(statements)
        left, right = st.columns(2)
        with left:
            chart(statement_frame.get("concept_label_raw", pd.Series(dtype=str)).map(clean)
                  .replace("", pd.NA).dropna().value_counts().head(15), "Top concepts")
            chart(statement_frame.get("actor_name_raw", pd.Series(dtype=str)).map(clean)
                  .replace("", pd.NA).dropna().value_counts().head(15), "Top actors")
        with right:
            chart(statement_frame.get("stance", pd.Series(dtype=str)).map(clean)
                  .replace("", pd.NA).dropna().value_counts(), "Stance")
            chart(statement_frame.get("network_layer", pd.Series(dtype=str)).map(clean)
                  .replace("", pd.NA).dropna().value_counts(), "Network layers")
    else:
        st.info("No statements for this selection.")

    spread = statement_spread(statements)
    st.markdown("**Who is named together**")
    st.caption(
        f"{spread['statements']} statements · {spread['actors']} distinct actors · "
        f"{spread['concepts']} distinct concept labels across {spread['records']} videos · "
        f"stance coded in {spread['with_stance']} · layers: {spread['layers']} · "
        f"actor types: {spread['actor_types']}.")
    st.info("Read this as co-mention, not as a social network. Every statement's concept is a free-text "
            "proposition — nearly one per statement — so an actor–concept graph would imply structure "
            "the data does not carry. Every actor is producer-typed \"Synthetic\": a position named in "
            "the text, not a verified person, and an edge means two names appear in the same video.")
    scoped = st.checkbox("Only the record open in the browser", value=False)
    open_record = clean(st.session_state.get("live_inspect"))
    chosen = [statement for statement in statements
              if not scoped or clean(statement.get("record_id")) == open_record]
    nodes, graph_edges = actor_comention_graph(chosen)
    figure = network_figure(nodes, graph_edges,
                            f"Actors named together · {len(nodes)} actors, {len(graph_edges)} pairs")
    if figure is None:
        st.info("No actor is named twice, so nothing co-occurs to draw. That is a fact about this "
                "selection, not a bug: DNA named "
                f"{spread['actors']} actors across {spread['statements']} statements.")
    else:
        st.plotly_chart(figure, use_container_width=True)
        st.dataframe(graph_edges.sort_values("videos", ascending=False)
                     .rename(columns={"source": "actor", "target": "co-mentioned with",
                                      "videos": "shared videos"}),
                     use_container_width=True)
        st.caption("Every pair above, with the number of videos both names appear in.")

with tabs[5]:
    st.subheader("Social network · step 8")
    st.caption("Nodes and edges as the producer wrote them, with the labels it assigned and the quote "
               "each edge was drawn from. A graph is a reading aid; the edge table is the evidence.")
    edges = child_records(ROOT, filtered, "sna_edges_json")
    nodes = child_records(ROOT, filtered, "sna_nodes_json")
    columns = st.columns(3)
    columns[0].metric("Edges", f"{len(edges):,}")
    columns[1].metric("Nodes", f"{len(nodes):,}")
    columns[2].metric("Videos with SNA", int(with_sna.sum()))
    if not edges:
        st.info("No SNA edges for this selection. Step 8 is partial in this export — that is a coverage "
                "fact, not a finding about the corpus.")
    else:
        edge_frame = pd.DataFrame(edges).astype(str)
        left, right = st.columns(2)
        with left:
            chart(counts_of(edge_frame, "edge_type"), "Edges by relation type")
            chart(counts_of(edge_frame, "network__layer".replace("__", "_")), "Edges by network layer")
            if "confidence" in edge_frame.columns:
                chart(pd.to_numeric(edge_frame["confidence"], errors="coerce").dropna()
                      .round(1).value_counts().sort_index(), "Edge confidence (rounded)")
        with right:
            chart(edge_frame["country"].str.casefold().value_counts()
                  if "country" in edge_frame.columns else None, "Edges by country")
            st.markdown("**Most connected actors**")
            st.dataframe(node_degrees(edges, nodes), width='stretch')
            if nodes:
                st.markdown("**Node types**")
                st.dataframe(pd.DataFrame(nodes).get("node_type", pd.Series(dtype=str))
                             .value_counts().rename_axis("node_type").reset_index(name="nodes"),
                             width='stretch')
        st.markdown("**Edges**")
        keys = [key for key in ("source_label", "target_label", "relation_type", "network_layer",
                                "confidence", "evidence_quote") if key in edge_frame.columns]
        table([{"record_id": item["record_id"],
                **{key: clean(item.get(key))[:220] for key in keys}} for item in edges],
              "sna_table", caption="Every edge carries the quote it was drawn from.")

with tabs[6]:
    st.subheader("Problems the producer recorded")
    st.caption("Every video whose status is not ok, with the reason the producer wrote beside it. "
               "Nothing here is inferred: an empty cell means it said nothing.")
    problems = problem_rows(filtered)
    if problems.empty:
        st.success("Every video in this selection reports ok on steps 1–7 and SNA.")
    else:
        st.metric("Videos with a non-ok stage", len(problems))
        st.dataframe(problems, width='stretch')
        reasons = [column for column in problems.columns if column not in
                   ("record_id", "country", "video_id", "not_complete")]
        for column in reasons:
            values = problems[column].map(clean)
            values = values[values != ""]
            if len(values):
                st.markdown(f"**{column}**")
                st.dataframe(values.value_counts().head(15).rename_axis("reason")
                             .reset_index(name="records"), width='stretch')

with tabs[7]:
    st.subheader("Aggregates over the current selection")
    st.caption("Counts over producer-coded fields. A sparse field means the stage did not run for "
               "that record, not that the entity is absent from the world.")
    left, right = st.columns(2)
    with left:
        chart(value_counts(filtered, "postprocess_entities", 15).set_index("value")["records"],
              "Top entities (summary stage)")
        chart(value_counts(filtered, "postprocess_themes", 15).set_index("value")["records"],
              "Top themes (summary stage)")
        chart(value_counts(filtered, "context_evidence_role", 10).set_index("value")["records"],
              "Evidence role")
    with right:
        st.markdown("**Sentiment targets (producer-coded)**")
        st.dataframe(sentiment_totals(filtered), width='stretch')
        chart(value_counts(filtered, "asr_language", 10).set_index("value")["records"],
              "ASR language")
        chart(value_counts(filtered, "author_username", 10).set_index("value")["records"],
              "Most frequent accounts")

with tabs[8]:
    st.subheader("Exports of the current selection")
    st.caption("Private research data: these files carry author usernames, video ids and transcripts. "
               "They are built from the filtered index and the bundle, and are not written anywhere "
               "on the server.")
    left, right = st.columns(2)
    left.download_button("Filtered index as CSV", filtered.to_csv(index=False),
                         file_name="live_steps_selection.csv", mime="text/csv")
    statements = child_records(ROOT, filtered, "dna_statements_json")
    right.download_button("DNA statements as CSV", statement_table(statements, limit=5000).to_csv(index=False),
                          file_name="live_steps_statements.csv", mime="text/csv",
                          disabled=not statements)

    st.divider()
    st.subheader("Data quality — what this build changed, and why")
    counts = manifest.get("record_counts") or {}
    rows = [{"country": country, "read": data.get("read"), "exported": data.get("exported"),
             "duplicates removed": data.get("duplicate_rows"),
             "invalid ids removed": data.get("invalid_ids"),
             "DNA statements": data.get("dna_statement_rows")}
            for country, data in counts.items() if isinstance(data, dict)]
    st.dataframe(pd.DataFrame(rows), width='stretch')
    source_bytes = sum(value.get("source_bytes", 0)
                       for value in (manifest.get("countries") or {}).values())
    st.caption(f"Duplicate rule: identity is (country, video_id); the row carrying the most stage "
               f"output wins. Source bytes {source_bytes / 1e6:.0f} MB → index + text bundle "
               f"{sum(value.get('bytes', 0) for value in (manifest.get('outputs') or [])) / 1e6:.0f} MB, "
               f"plus the cleaned frames this repository also stores as ordinary CSV.")
    dropped = (manifest.get("inputs") or {}).get("finland", {}).get("dropped_reasons") or {}
    st.markdown(f"**Dropped source columns ({len(dropped)}) and why**")
    st.dataframe(pd.DataFrame([{"column": key, "reason": value} for key, value in sorted(dropped.items())]),
                 width='stretch')
    failures = manifest.get("parse_failures") or {}
    if any(any(values.values()) for values in failures.values() if isinstance(values, dict)):
        st.warning("Unparseable JSON cells in the export: " + str(failures))
    else:
        st.success("Every structured child cell in the export parsed.")
    cleaned_frames = manifest.get("cleaned_frames") or {}
    if cleaned_frames:
        st.markdown("**Cleaned dataframes** (the whole frame, ordinary CSV, in the private repository)")
        st.write(cleaned_frames)

with tabs[9]:
    st.subheader("Data and methods")
    for key in ("contract", "builder_version", "generated_at", "record_unit", "records", "read_only"):
        st.write(f"**{key}**: {manifest.get(key)}")
    st.markdown("**Derivations, stated once**")
    st.write({"record_date": "from the media id token YYYYMMDD — not a producer field",
              "month": "first seven characters of record_date",
              "pipeline_steps_ok": "count of step_01…step_07 statuses in ok/complete/cached",
              "has_sna": "step 8 edges present in the text bundle",
              "duplicates": "collapsed on (country, video_id), completeness-biased"})
    st.markdown("**Reader**")
    st.write(manifest.get("reader") or "not recorded")
    st.markdown("**Per-country source files**")
    st.dataframe(pd.DataFrame([{"country": country, **data}
                               for country, data in (manifest.get("countries") or {}).items()]),
                 width='stretch')
    st.caption("Nothing here is written back to the canonical records, and no chart is a finding: "
               "the status fields prove a stage ran, not that its interpretation is right.")


with tabs[10]:
    render_stage_explorer(ROOT, filtered)
