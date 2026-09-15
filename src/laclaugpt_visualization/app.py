"""Streamlit dashboard for researcher-facing exploration."""
from __future__ import annotations

from pathlib import Path

import plotly.express as px
import streamlit as st

from .config import get_settings
from .data import explode_labels, filter_frame, load_frame
from .storage import load_mongodb`nfrom .transforms import monitor`nfrom .review import Review, SQLiteReviewStore


def _load_default_frame():
    settings = get_settings()
    if settings.data_backend == "mongodb":
        return load_mongodb(settings)

    candidates = sorted(settings.data_dir.glob("*.csv")) + sorted(settings.data_dir.glob("*.jsonl"))
    if settings.data_backend == "sqlite" and settings.sqlite_path.exists():
        return load_frame(settings.sqlite_path, settings)
    if not candidates:
        return None
    return load_frame(candidates[0], settings)


def run() -> None:
    st.set_page_config(page_title="LaclauGPT Data Visualization", layout="wide")
    st.title("LaclauGPT Data Visualization")
    st.caption("Local-first researcher dashboard. Remote services are optional.")`n    st.warning("Counts, confidence, graph degree and chart layout are descriptive aids, not evidence of hegemony, nodal status, empty signification or antagonism. Researchers must inspect evidence and review status.")

    frame = _load_default_frame()
    uploaded = st.sidebar.file_uploader("Open CSV or JSONL", type=["csv", "jsonl", "ndjson"])
    if uploaded is not None:
        temp = Path(".laclaugpt-upload") / uploaded.name
        temp.parent.mkdir(parents=True, exist_ok=True)
        temp.write_bytes(uploaded.getvalue())
        frame = load_frame(temp)

    if frame is None or frame.empty:
        st.info("Add a CSV/JSONL file under data/, configure SQLite, or enable MongoDB.")
        return

    query = st.sidebar.text_input("Search")
    platforms = sorted(frame["source_platform"].dropna().unique().tolist())
    selected_platforms = st.sidebar.multiselect("Platforms", platforms)
    filtered = filter_frame(frame, query=query, platforms=selected_platforms)

    c1, c2, c3 = st.columns(3)
    c1.metric("Documents", len(filtered))
    c2.metric("Platforms", filtered["source_platform"].nunique())
    c3.metric("Authors", filtered["source_author"].nunique())

    tabs = st.tabs(["Monitor", "Researcher Review", "Explore", "Signifiers", "Discourses", "Documents"])
    with tabs[0]:
        topics = explode_labels(filtered, "topics").head(20)
        if not topics.empty:
            st.plotly_chart(px.bar(topics, x="count", y="topics", orientation="h", title="Top topics"), use_container_width=True)
        else:
            st.info("No topic labels in the current selection.")
    with tabs[1]:
        values = explode_labels(filtered, "signifiers").head(30)
        if not values.empty:
            st.plotly_chart(px.bar(values, x="count", y="signifiers", orientation="h"), use_container_width=True)
        else:
            st.info("No signifiers in the current selection.")
    with tabs[2]:
        values = explode_labels(filtered, "discourses").head(30)
        if not values.empty:
            st.plotly_chart(px.bar(values, x="count", y="discourses", orientation="h"), use_container_width=True)
        else:
            st.info("No discourse labels in the current selection.")
    with tabs[3]:
        columns = [column for column in ("document_id", "source_author", "source_platform", "summary") if column in filtered]
        st.dataframe(filtered[columns], use_container_width=True, hide_index=True)


if __name__ == "__main__":
    run()


