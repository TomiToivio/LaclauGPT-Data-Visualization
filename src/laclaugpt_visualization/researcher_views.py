"""Researcher-facing, read-only evidence presentation for the existing live-steps contract.

No sensitive research data, inferred findings, or server specifics belong in this module.
The export's step numbering is authoritative: 1 ASR, 2 OCR, 3 frames, 4 video,
5 summary/postprocess, 6 Laclau discourse, 7 discourse network analysis (DNA).
"""
from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any, Mapping

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from laclaugpt_visualization.live_steps import STEPS, bundle_text, clean

FRIENDLY_FIELDS = {
    "asr_transcript": "Original transcript",
    "asr_translated": "Translated transcript",
    "ocr_1": "Text visible on screen (OCR)",
    "frame_analysis_1": "Frame and image interpretation",
    "vllm_video_analysis": "Video interpretation",
    "vllm_video_markdown_analysis": "Video analysis (formatted)",
    "summary_analysis": "Multimodal synthesis",
    "summary_summary_md": "Researcher-readable summary",
    "postprocess_summary_md": "Postprocessed summary",
    "laclau_structured_json": "Structured discourse interpretation",
    "laclau_summary_md": "Discourse interpretation",
    "dna_analysis_markdown": "Discourse-network interpretation",
    "dna_statements_json": "Actor–concept statements with evidence",
}
STEP_HELP = {
    1: "Automatic speech recognition and translated speech, where present.",
    2: "Optical character recognition, including text visible in the video.",
    3: "Model interpretations of sampled video frames; inspect alongside the source.",
    4: "Model interpretation of the video and its multimodal context.",
    5: "Synthesis and postprocessing, including extracted themes and entities.",
    6: "Laclaudian interpretations: provisional analytical codings, not ground truth.",
    7: "Discourse Network Analysis statements (actor, concept and stance) and their evidence.",
}
STATUS_FIELDS = {step: f"step_{step:02d}_status" for step in range(1, 8)}


def status_label(value: Any) -> str:
    """Preserve the producer's status; report missingness, never invent success."""
    return clean(value) or "Not reported / unavailable"


def readable_value(value: Any) -> Any:
    """Parse structured JSON only when valid; leave malformed content verbatim."""
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("{", "[")):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            pass
    return value


def evidence_fields(step: int, row: Mapping[str, Any], bundle: Mapping[str, Any]) -> list[tuple[str, Any]]:
    """All declared text AND index outputs for this step, with no missing values invented."""
    _, text_fields, index_fields = STEPS[step]
    output = []
    for field in (*text_fields, *index_fields):
        value = bundle.get(field, row.get(field))
        if value is not None and clean(value) and value != [] and value != {}:
            output.append((field, readable_value(value)))
    return output


def statement_links(statements: list[dict], limit: int = 70) -> list[tuple[str, str, int]]:
    """Observed actor–concept links for visualization, not inferred relationships."""
    counts: Counter[tuple[str, str]] = Counter()
    for item in statements:
        actor = clean(item.get("actor_name_raw") or item.get("actor"))
        concept = clean(item.get("concept") or item.get("concept_name_raw"))
        if actor and concept:
            counts[(actor, concept)] += 1
    return [(actor, concept, weight) for (actor, concept), weight in counts.most_common(limit)]


def dna_network_figure(statements: list[dict]) -> go.Figure | None:
    """Small deterministic bipartite graph; full evidence remains in the table."""
    links = statement_links(statements)
    if not links:
        return None
    actors = sorted({actor for actor, _, _ in links})
    concepts = sorted({concept for _, concept, _ in links})
    nodes = [("actor", item) for item in actors] + [("concept", item) for item in concepts]
    positions = {}
    for kind, names, x in (("actor", actors, 0), ("concept", concepts, 1)):
        for i, name in enumerate(names):
            positions[(kind, name)] = (x, i - (len(names) - 1) / 2)
    fig = go.Figure()
    for actor, concept, weight in links:
        a, b = positions[("actor", actor)], positions[("concept", concept)]
        fig.add_trace(go.Scatter(x=[a[0], b[0]], y=[a[1], b[1]], mode="lines",
                                 line={"width": min(5, 1 + math.log1p(weight)), "color": "#9e9e9e"},
                                 hoverinfo="text", text=f"{weight} statement(s)",
                                 showlegend=False))
    for kind, names, color in (("actor", actors, "#3e78b2"), ("concept", concepts, "#bc6b8e")):
        fig.add_trace(go.Scatter(
            x=[positions[(kind, name)][0] for name in names],
            y=[positions[(kind, name)][1] for name in names],
            mode="markers+text", text=[name[:36] for name in names],
            textposition="middle right" if kind == "actor" else "middle left",
            marker={"size": 10, "color": color},
            name=kind.title(), customdata=names,
            hovertemplate="%{customdata}<extra></extra>"))
    fig.update_layout(height=max(360, min(1000, 35 * max(len(actors), len(concepts)))),
                      xaxis={"visible": False, "range": [-0.4, 1.4]},
                      yaxis={"visible": False}, showlegend=True,
                      margin={"l": 30, "r": 30, "t": 15, "b": 15})
    return fig


def render_field(field: str, value: Any, *, key: str) -> None:
    st.markdown(f"**{FRIENDLY_FIELDS.get(field, field.replace('_', ' ').capitalize())}**")
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            st.dataframe(pd.DataFrame(value).astype(str), use_container_width=True)
        elif value:
            st.write(value)
        else:
            st.info("No entries reported.")
    elif isinstance(value, dict):
        st.json(value, expanded=False)
    else:
        text = str(value)
        if len(text) > 20000:
            st.caption("Preview of first 20,000 characters; full value remains in the source artifact.")
            st.text_area("Evidence preview", text[:20000], height=250, key=key)
        elif "\n" in text or len(text) > 240:
            st.text_area("Evidence", text, height=min(420, max(120, len(text) // 5)),
                         key=key)
        else:
            st.write(text)


def render_stage_explorer(root: str, filtered: pd.DataFrame) -> None:
    """Per-stage evidence for a selected record; obey the same sidebar filters."""
    st.subheader("Step-by-step evidence explorer")
    st.caption("Select a video, then a producer stage. Every field shown comes from the index or "
               "verbatim linked bundle. Empty and missing values are not negative findings.")
    if filtered.empty:
        st.info("No videos match the current filters.")
        return
    ids = filtered["record_id"].astype(str).tolist()
    preferred = st.session_state.get("live_inspect", "")
    index = ids.index(preferred) if preferred in ids else 0
    selected = st.selectbox("Video record", range(len(ids)), index=index,
                            format_func=lambda n: f"{filtered.iloc[n].get('country', '')} · "
                                                  f"{filtered.iloc[n].get('video_id', ids[n])}",
                            key="researcher_video")
    row = filtered.iloc[selected].to_dict()
    record_id = ids[selected]
    stage = st.selectbox("Analysis stage",
                         list(range(1, 8)),
                         format_func=lambda n: f"{n}. {STEPS[n][0]}",
                         key="researcher_stage")
    st.caption(STEP_HELP[stage])
    st.write(f"**Producer status:** {status_label(row.get(STATUS_FIELDS[stage]))}")
    long_fields = [field for _, fields, _ in STEPS.values() for field in fields]
    bundle = bundle_text(root, long_fields).get(record_id, {})
    evidence = evidence_fields(stage, row, bundle)
    if not evidence:
        st.info("No exported output for this stage and record. Check stage coverage and producer status.")
    for n, (field, value) in enumerate(evidence):
        render_field(field, value, key=f"stage_{stage}_{selected}_{n}")
    if stage == 7:
        raw = readable_value(bundle.get("dna_statements_json", ""))
        if isinstance(raw, list):
            statements = [item for item in raw if isinstance(item, dict)]
            fig = dna_network_figure(statements)
            if fig is not None:
                st.markdown("**Observed actor–concept links (this record only)**")
                st.plotly_chart(fig, use_container_width=True)
                st.caption("An exploratory diagram of recorded statements, not a causal or social network.")
            elif statements:
                st.info("No actor–concept pairs available to draw; statement evidence is shown above.")
    st.caption("Machine-generated interpretations require scholarly verification. "
               "Producer political categories and names are source metadata, not conclusions.")
