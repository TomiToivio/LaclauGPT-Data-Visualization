"""One Streamlit application with Monitor, Researcher Review and Explore modes."""
from __future__ import annotations

from pathlib import Path

import plotly.express as px
import streamlit as st

from .config import get_settings
from .data import filter_frame, load_frame
from .review import Review, SQLiteReviewStore
from .storage import load_mongodb
from .transforms import explore, graph_projection, monitor, relations

CAVEAT = (
    "Counts, confidence, graph degree and layout are descriptive aids. They do not by "
    "themselves establish hegemony, nodal status, empty/floating signification, antagonism "
    "or theoretical validity. Inspect evidence and human review state."
)


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
            candidates.extend(sorted(Path(root).glob("*.jsonl")))
            candidates.extend(sorted(Path(root).glob("*.ndjson")))
            candidates.extend(sorted(Path(root).glob("*.csv")))
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
    for key, title in (("formations", "Formations"), ("signifiers", "Signifiers"), ("actors", "Actors")):
        table = values[key]
        if not table.empty:
            label_column = table.columns[0]
            st.plotly_chart(
                px.bar(table.head(20), x="count", y=label_column, orientation="h", title=title),
                use_container_width=True,
            )
    st.caption(CAVEAT)


def _review_page(frame) -> None:
    if frame.empty:
        st.info("No records in the current view.")
        return
    settings = get_settings()
    store = SQLiteReviewStore(settings.data_path("database", "reviews.sqlite3"))
    options = frame["source_url"].fillna("").astype(str).tolist()
    source_url = st.selectbox("Record", options)
    row = frame[frame["source_url"] == source_url].iloc[0]
    st.subheader(row.get("summary") or source_url)
    st.caption(f"{row.get('source_platform', '')} · {row.get('source_author', '')}")
    st.markdown("#### Transcript")
    st.text(row.get("transcript") or "No transcript")
    if row.get("ocr"):
        st.markdown("#### OCR")
        st.write(row.get("ocr"))
    if row.get("frames"):
        st.markdown("#### Multimodal/frame evidence")
        st.write(row.get("frames"))
    st.markdown("#### Structured analysis")
    st.json(
        {
            key: row.get(key)
            for key in (
                "entities", "topics", "formations", "signifiers", "discourses", "frontier",
                "uncertainties", "abstentions", "provenance"
            )
            if key in row
        }
    )
    existing = store.get(source_url) or Review(source_url=source_url)
    status = st.selectbox(
        "Review status",
        ["PROVISIONAL", "ACCEPTED", "REJECTED", "REVISED", "CANONICAL", "SUPERSEDED"],
        index=["PROVISIONAL", "ACCEPTED", "REJECTED", "REVISED", "CANONICAL", "SUPERSEDED"].index(existing.status),
    )
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
        st.plotly_chart(px.line(timeline, x="period", y="documents", markers=True), use_container_width=True)
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
    st.caption(f"Graph projection: {len(projection['nodes'])} nodes, {len(projection['edges'])} edges")
    st.caption(CAVEAT)


def run() -> None:
    st.set_page_config(page_title="LaclauGPT Data Visualization", layout="wide")
    st.title("LaclauGPT Data Visualization")
    st.caption("Canonical monitor + researcher workbench + exploration layer.")
    st.warning(CAVEAT)
    settings = get_settings()
    settings.ensure_local_directories()
    frame = _load_default_frame()
    uploaded = st.sidebar.file_uploader("Open CSV, JSON or JSONL", type=["csv", "json", "jsonl", "ndjson"])
    if uploaded is not None:
        temp = settings.data_path("tmp", "uploads", uploaded.name)
        temp.parent.mkdir(parents=True, exist_ok=True)
        temp.write_bytes(uploaded.getvalue())
        frame = load_frame(temp)
    if frame is None or frame.empty:
        st.info("Add canonical CSV/JSONL under data/, configure Analysis data root, SQLite, or MongoDB.")
        return
    filtered = _sidebar_filters(frame)
    monitor_tab, review_tab, explore_tab = st.tabs(["Monitor", "Researcher Review", "Explore"])
    with monitor_tab:
        _monitor_page(filtered)
    with review_tab:
        _review_page(filtered)
    with explore_tab:
        _explore_page(filtered)


if __name__ == "__main__":
    run()
