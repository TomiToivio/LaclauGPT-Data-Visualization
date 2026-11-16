"""Versioned, fail-closed researcher presentation of EP24 exports (no inference)."""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from laclaugpt_visualization.ep24_reprocessed import identity, text, unpack

DISPLAY_VERSION = "ep24-researcher-display/1"
# Public field mapping doubles as the display/export allowlist. Never use producer prefixes.
FIELDS = {
    "country": "Country",
    "source_type": "Platform",
    "source_platform": "Source platform",
    "source_url": "Video link",
    "title": "Title",
    "caption": "Caption",
    "author_username": "Creator",
    "published_at": "Published date",
    "created_at": "Created date",
    "source_recording": "Recording date",
    "source_language": "Language",
    "language": "Source language",
    "duration_seconds": "Duration (seconds)",
    "video_duration": "Video duration",
    "political_preference": "Source political preference",
    "asr_transcript": "Original transcript",
    "whisper_transcript": "Legacy transcript",
    "asr_translation": "Translated transcript",
    "asr_translated": "Translation",
    "whisper_translation": "Legacy translation",
    "ocr_1": "Text visible in video",
    "frame_analysis_1": "Frame interpretation",
    "vllm_video_analysis": "Video observations",
    "vllm_video_markdown_analysis": "Temporal video interpretation",
    "summary_analysis": "Multimodal summary",
    "summary_summary_md": "Summary",
    "postprocess_summary_md": "Postprocess interpretation",
    "postprocess_entities": "Entities",
    "entities": "Legacy entities",
    "postprocess_themes": "Themes",
    "themes": "Legacy themes",
    "topics": "Topics",
    "positive": "Positive sentiment",
    "neutral": "Neutral sentiment",
    "negative": "Negative sentiment",
    "laclau_summary_md": "Discourse interpretation",
    "laclau_structured_json": "Discourse concepts and evidence",
    "laclau_abstention_reason": "Discourse abstention",
    "formula_of_populism_analysis": "Formula of populism",
    "dna_analysis_markdown": "DNA interpretation",
    "dna_statements_json": "DNA statements",
    "sna_analysis_markdown": "SNA interpretation",
    "sna_nodes_json": "SNA actors",
    "sna_edges_json": "SNA evidenced ties",
    "researcher_note": "Researcher annotation",
    "summary_quality_status": "Summary quality",
    "summary_quality_reason": "Quality explanation",
    "laclau_status": "Discourse availability",
    "dna_status": "DNA availability",
}
# Nested output is also explicitly projected: wrappers/debug fields cannot leak through a safe column.
DETAIL_KEYS = {
    "name",
    "label",
    "text",
    "quote",
    "quotation",
    "evidence",
    "evidence_quote",
    "evidence_text",
    "actor",
    "actor_name",
    "actor_name_raw",
    "concept",
    "concept_name",
    "concept_name_raw",
    "stance",
    "position",
    "sentiment",
    "target",
    "source",
    "relation_type",
    "description",
    "summary",
    "interpretation",
    "confidence",
    "uncertainty",
    "status",
    "reason",
    "demands",
    "signifiers",
    "nodal_points",
    "empty_signifiers",
    "floating_signifiers",
    "collective_identities",
    "antagonisms",
    "affects",
    "equivalence_chains",
    "political_frontiers",
    "us",
    "them",
    "frontier",
    "statements",
    "nodes",
    "edges",
    "entities",
    "themes",
    "topics",
    "type",
    "role",
    "start",
    "end",
    "timestamp_seconds",
    "original",
    "translation",
}
COUNTRIES = {
    "fi": "Finland",
    "finland": "Finland",
    "pl": "Poland",
    "poland": "Poland",
    "pt": "Portugal",
    "portugal": "Portugal",
}


def readable(value):
    """Render allowed structured content as readable text, never arbitrary object dumps."""
    value = unpack(value)
    if isinstance(value, Mapping):
        return "\n".join(
            f"{key.replace('_', ' ').capitalize()}: {readable(part)}"
            for key, part in value.items()
            if key in DETAIL_KEYS and readable(part)
        )
    if isinstance(value, list):
        return "\n".join(f"• {readable(part)}" for part in value if readable(part))
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        return "Structured output could not be decoded; inspect authorized provenance."
    return text(value)


def researcher_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    for field, label in FIELDS.items():
        if field in frame:
            result[label] = frame[field].map(readable)
    if "Country" in result:
        result["Country"] = result["Country"].map(lambda x: COUNTRIES.get(x.casefold(), x))
    return result


def researcher_csv(frame: pd.DataFrame) -> bytes:
    safe = researcher_frame(frame)
    # Quoting alone does not stop spreadsheet formula execution.
    for col in safe:
        safe[col] = safe[col].map(
            lambda x: "'" + x if x.lstrip().startswith(("=", "+", "-", "@")) else x
        )
    return safe.to_csv(index=False).encode("utf-8-sig")


def hydrate_record(root: str | Path, row: Mapping) -> dict:
    """Load long evidence lazily for one selected video, supporting both existing bundle shapes."""
    result = dict(row)
    key = text(row.get("record_id")) or text(row.get("record_key")) or identity(row)
    for folder in (Path(root), Path(root) / "data"):
        paths = sorted(folder.glob("*_text.jsonl.gz")) or list(folder.glob("text.jsonl.gz"))
        for path in paths:
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                for line in stream:
                    payload = json.loads(line)
                    if (payload.get("record_id") or payload.get("record_key")) != key:
                        continue
                    for field, value in payload.items():
                        if field in FIELDS:
                            result[field] = value
                        elif isinstance(value, dict):
                            result.update({k: v for k, v in value.items() if k in FIELDS})
                    return result
    return result


def render_inspector(root, row):
    import streamlit as st

    if not row:
        return
    row = hydrate_record(root, row)
    st.subheader("Video evidence")
    st.caption(
        "Transcript/OCR reproduce source content. Model summaries and analytical coding "
        "are interpretations; researcher annotations are separate. Missing is not negative."
    )
    shown = researcher_frame(pd.DataFrame([row])).iloc[0]
    for label, value in shown.items():
        if value:
            with st.expander(label):
                st.text(value)
    if not text(row.get("researcher_note")):
        st.caption("Researcher annotation: unavailable. Analysis is not assumed to be reviewed.")


def render_overview(frame, total):
    import plotly.express as px
    import streamlit as st

    safe = researcher_frame(frame)
    st.metric("Videos matching filters", len(frame))
    st.caption(
        f"Denominator: {total:,} videos in the loaded export; {len(frame):,} match filters. "
        "Counts and centrality do not establish hegemony."
    )
    for label in ("Country", "Platform", "Language", "Source political preference"):
        if label not in safe or not safe[label].ne("").any():
            continue
        counts = (
            safe[label]
            .replace("", "Unavailable")
            .value_counts()
            .rename_axis(label)
            .reset_index(name="Videos")
        )
        fig = px.bar(counts, x=label, y="Videos", title=f"Videos by {label.lower()}")
        event = st.plotly_chart(fig, on_select="rerun", key=f"overview_{label}")
        points = event.selection.points
        if points:
            chosen = points[0]["x"]
            members = safe[label].replace("", "Unavailable").eq(chosen)
            st.caption("Source videos underlying the selected bar")
            st.dataframe(safe.loc[members], hide_index=True)
    date = next(
        (c for c in ("Published date", "Created date", "Recording date") if c in safe), None
    )
    if date:
        dates = pd.to_datetime(safe[date], errors="coerce", utc=True)
        st.caption(
            f"Publication timeline: {dates.notna().sum()} dated videos; "
            f"{dates.isna().sum()} unavailable dates."
        )
        counts = dates.dt.date.value_counts().sort_index()
        if not counts.empty:
            st.line_chart(counts.rename("Videos"))


def render_browser(frame):
    import streamlit as st

    safe = researcher_frame(frame)
    query = st.text_input("Search video content")
    if query and len(safe.columns):
        safe = safe[
            safe.apply(lambda col: col.str.contains(query, case=False, regex=False)).any(axis=1)
        ]
    defaults = [
        c
        for c in ("Country", "Platform", "Title", "Creator", "Language", "Video link")
        if c in safe
    ]
    columns = st.multiselect(
        "Visible columns", list(safe.columns), default=defaults or list(safe.columns)[:6]
    )
    if not columns:
        st.info("Select at least one display column.")
        return
    sort = st.selectbox("Sort by", columns)
    safe = safe.sort_values(sort, kind="stable")
    page_size = st.selectbox("Videos per page", [25, 50, 100])
    pages = max(1, (len(safe) + page_size - 1) // page_size)
    page = st.number_input("Page", min_value=1, max_value=pages, value=1)
    page_frame = safe.iloc[(page - 1) * page_size : page * page_size]
    event = st.dataframe(
        page_frame[columns], hide_index=True, on_select="rerun", selection_mode="single-row"
    )
    if event.selection.rows:
        index = page_frame.index[event.selection.rows[0]]
        st.session_state["ep24_inspect"] = identity(frame.loc[index].to_dict())
    st.caption(f"{len(safe)} matching videos · page {page} of {pages}")
    st.download_button(
        "Download searched videos", researcher_csv(frame.loc[safe.index]), "ep24_search.csv"
    )
