"""NoöPunk-inspired researcher presentation for canonical AI26 view frames.

Only display transforms live here. No new coding, actor identity resolution, or inference.
All charts operate on the caller's already-filtered bounded snapshot.
"""
from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import pandas as pd

PALETTE = ["#47d7e8", "#ad91ff", "#ffb86b", "#ff80bb", "#7de2a8", "#e8e88d"]
MISSING = "(Unavailable)"
BROWSER_FIELDS = {
    "content_title": "Title",
    "source_author": "Author / account",
    "source_platform": "Source",
    "source_timestamp": "Published (UTC)",
    "source_language": "Language",
    "source_country": "Country / region",
    "analysis_status": "Analysis status",
    "review_status": "Review status",
}
DETAIL_FIELDS = {
    "formations": "Provisional formations",
    "signifiers": "Candidate signifiers",
    "nodal_points": "Candidate nodal points",
    "topics": "Topics",
    "entities": "Entities",
    "imaginaries": "Imaginaries",
    "discourses": "Discourses",
    "us": "Collective subjects (Us)",
    "them": "Them",
    "frontier": "Frontier candidates",
    "affects": "Affects",
    "uncertainties": "Uncertainty",
    "abstentions": "Abstentions",
    "evidence": "Evidence",
}
# Intentionally exclude internal IDs, hashes, run manifests and arbitrary backend payloads.
DETAIL_KEYS = frozenset({
    "name", "label", "text", "quote", "quotation", "evidence", "evidence_quote",
    "evidence_text", "description", "summary", "interpretation", "confidence",
    "uncertainty", "status", "reason", "kind", "type", "role", "start", "end",
    "selector", "value", "context", "explanation", "evidence_span",
    "source", "target", "polarity", "stance", "position", "message", "excerpt",
})


def readable(value: Any) -> str:
    """Format approved fields as literal plain text; do not dump arbitrary nested objects."""
    if isinstance(value, Mapping):
        parts = []
        for key, item in value.items():
            if key in DETAIL_KEYS and (shown := readable(item)):
                parts.append(f"{key.replace('_', ' ').capitalize()}: {shown}")
        return "\n".join(parts)
    if isinstance(value, (list, tuple)):
        return "\n".join(f"• {item}" for part in value if (item := readable(part)))
    if value is None or value is pd.NA:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (ValueError, TypeError):
        return ""
    return str(value).strip()


def utc_dates(frame: pd.DataFrame) -> pd.Series:
    """Publication clock only, with original missing dates left missing."""
    if "source_timestamp" not in frame:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    return pd.to_datetime(frame["source_timestamp"], utc=True, format="mixed", errors="coerce")


def researcher_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Project the researcher-visible allowlist; never fall back to the raw frame."""
    table = pd.DataFrame(index=frame.index)
    for field, label in BROWSER_FIELDS.items():
        if field in frame:
            if field == "source_timestamp":
                table[label] = utc_dates(frame).dt.strftime("%Y-%m-%d %H:%M").fillna("")
            else:
                table[label] = frame[field].map(readable)
    return table


def category_counts(frame: pd.DataFrame, field: str) -> pd.DataFrame:
    """Count records, explicitly retaining the missing category."""
    if field not in frame:
        return pd.DataFrame({"Label": [MISSING], "Records": [len(frame)]}) if len(frame) else (
            pd.DataFrame(columns=["Label", "Records"])
        )
    return (
        frame[field].map(readable).replace("", MISSING).value_counts()
        .rename_axis("Label").reset_index(name="Records")
    )


def publication_activity(frame: pd.DataFrame) -> pd.DataFrame:
    """Observed publication counts by UTC day and source (no fabricated zero-filled days)."""
    dates = utc_dates(frame)
    platform = (
        frame["source_platform"].map(readable).replace("", MISSING)
        if "source_platform" in frame else pd.Series(MISSING, index=frame.index)
    )
    activity = pd.DataFrame({"Day": dates.dt.floor("D"), "Source": platform})
    return (
        activity.dropna(subset=["Day"]).groupby(["Day", "Source"], as_index=False)
        .size().rename(columns={"size": "Records"})
    )


def overlap_matrix(cross: pd.DataFrame, limit: int = 12) -> pd.DataFrame:
    """Convert already-computed co-occurrence counts to a bounded display matrix.

    Missing cells mean no observed co-occurrence within the supplied table; they do not
    establish opposition or nonexistence outside the current filtered snapshot.
    """
    if cross.empty:
        return pd.DataFrame()
    formations = cross.groupby("formation")["count"].sum().nlargest(limit).index
    signifiers = cross.groupby("signifier")["count"].sum().nlargest(limit).index
    visible = cross[cross["formation"].isin(formations) & cross["signifier"].isin(signifiers)]
    return (
        visible.pivot_table(index="formation", columns="signifier", values="count", aggfunc="sum")
        .reindex(index=formations, columns=signifiers).fillna(0).astype(int)
    )


def chart_style(figure):
    """High-contrast data-art styling without using color as a scientific variable."""
    figure.update_layout(
        template="plotly_dark",
        paper_bgcolor="#10172b",
        plot_bgcolor="#10172b",
        font={"color": "#eff3ff", "size": 13},
        colorway=PALETTE,
        margin={"l": 18, "r": 24, "t": 40, "b": 28},
        hoverlabel={"bgcolor": "#10172b", "font_color": "#eff3ff"},
    )
    figure.update_xaxes(gridcolor="#293657", zerolinecolor="#53617b")
    figure.update_yaxes(gridcolor="#293657", zerolinecolor="#53617b")
    return figure


def valid_revision(value: str) -> str | None:
    """Accept only a hexadecimal Git revision, never paths or environment secrets."""
    return value.lower() if re.fullmatch(r"[0-9a-fA-F]{7,40}", value) else None


@lru_cache(maxsize=1)
def release_revision() -> tuple[str, str]:
    """Report deployment metadata or the checkout revision at first render."""
    declared = valid_revision(os.environ.get("LACLAUGPT_VIS_RELEASE_SHA", ""))
    if declared:
        return declared, "Deployment revision"
    root = Path(__file__).resolve().parents[2]
    if (root / ".git").exists() and (root / "src" / __package__).is_dir():
        try:
            command = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
                check=True, capture_output=True, text=True, timeout=1,
            )
            revision = valid_revision(command.stdout.strip())
            if revision:
                return revision, "Checkout revision at first render"
        except (OSError, subprocess.SubprocessError):
            pass
    return "", "Release revision unavailable"


def source_link(source: str) -> str | None:
    """Construct a safe Markdown URL only for ordinary HTTP(S) source identities."""
    try:
        parsed = urlsplit(source)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            return quote(source, safe=":/?#[]@!*+,;=%")
    except ValueError:
        pass
    return None


def render_header():
    import streamlit as st

    # Fixed text, no source data interpolated into HTML.
    st.markdown(
        """
        <div style="background:linear-gradient(115deg,#10172b,#312658);
          border:1px solid #6875a8;border-left:5px solid #47d7e8;border-radius:12px;
          padding:20px;color:#eff3ff">
          <div style="color:#47d7e8;letter-spacing:.12em;font-size:.8rem;font-weight:700">
            LACLAUGPT / AI26 · NOÖPUNK RESEARCH INTERFACE</div>
          <div style="font-size:1.7rem;font-weight:700;margin:.4rem 0">
            Mapping ideological contestation over AI</div>
          <div>Start with the corpus overview, follow the candidate concepts and
            networks, then inspect the source evidence.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    revision, label = release_revision()
    st.caption(f"{label}: {revision[:12]}" if revision else label)


def render_corpus_charts(frame: pd.DataFrame):
    import plotly.express as px
    import streamlit as st

    if frame.empty:
        st.info("No records match the current filters. Change a filter to explore the corpus.")
        return
    st.markdown("#### Coverage and publication activity")
    dates = utc_dates(frame)
    if dates.notna().any():
        st.caption(
            f"Publication span: {dates.min():%d %b %Y} – {dates.max():%d %b %Y} (UTC). "
            f"{dates.isna().sum():,} of {len(frame):,} visible records have no valid publication date."
        )
    else:
        st.caption("No valid publication dates in the current filtered window.")
    activity = publication_activity(frame)
    if not activity.empty:
        totals = activity.groupby("Source")["Records"].sum().nlargest(10)
        visible = activity[activity["Source"].isin(totals.index)]
        st.plotly_chart(
            chart_style(px.bar(visible, x="Day", y="Records", color="Source",
                               color_discrete_sequence=PALETTE)),
            width="stretch",
            key="ai26_publication_activity",
        )
        st.caption(
            f"Top {len(totals)} sources account for {visible['Records'].sum():,} "
            f"of {len(frame):,} filtered records. Undated records are excluded here."
        )
    for column, (field, title) in zip(
        st.columns(3),
        (("source_platform", "Source mix"), ("analysis_status", "Analysis availability"),
         ("review_status", "Review state")),
        strict=True,
    ):
        counts = category_counts(frame, field)
        if counts.empty:
            continue
        shown = counts.head(12).iloc[::-1]
        column.plotly_chart(
            chart_style(px.bar(shown, x="Records", y="Label", orientation="h",
                               title=title, text="Records")),
            width="stretch",
            key=f"ai26_coverage_{field}",
        )
        column.caption(f"{shown['Records'].sum():,} of {len(frame):,} records shown.")


def render_evidence(frame: pd.DataFrame, sources: list[str], key: str):
    """Open the corresponding source rows; source URLs are retained but not used as labels."""
    import streamlit as st

    if "source_url" not in frame or not sources:
        st.caption("No stable source identities are available for this selection.")
        return
    rows = frame.loc[frame["source_url"].isin(sources)]
    st.caption(f"{len(rows):,} loaded records underlie this selection.")
    table = researcher_table(rows)
    if len(table.columns):
        st.dataframe(table.head(100), hide_index=True, width="stretch")
    render_record_picker(rows, key)


def render_overlap(frame: pd.DataFrame, cross: pd.DataFrame):
    import plotly.express as px
    import streamlit as st

    matrix = overlap_matrix(cross)
    if matrix.empty:
        st.info("No formation/signifier overlap is available in the current view.")
        return
    fig = px.imshow(
        matrix, color_continuous_scale=["#17223e", "#5647a1", "#47d7e8"],
        aspect="auto", labels={"color": "Co-occurrences", "x": "Signifier", "y": "Formation"},
    )
    st.plotly_chart(chart_style(fig), width="stretch", key="ai26_overlap_heatmap")
    st.caption(
        "Up to 12 frequent formations and 12 frequent signifiers. The cells count observed "
        "co-occurrences, not ideological identity, equivalence or hegemony."
    )
    formation = st.selectbox("Inspect formation", matrix.index.tolist(), key="ai26_overlap_formation")
    signifier = st.selectbox("Inspect signifier", matrix.columns.tolist(), key="ai26_overlap_signifier")
    cells = cross[cross["formation"].eq(formation) & cross["signifier"].eq(signifier)]
    sources = list(dict.fromkeys(s for group in cells["source_urls"] for s in group))
    render_evidence(frame, sources, "ai26_overlap_record")


def render_record_picker(frame: pd.DataFrame, key: str):
    import streamlit as st

    if "source_url" not in frame:
        return
    options = [
        url for url in frame["source_url"].unique()
        if isinstance(url, str) and url.strip()
    ]
    if not options:
        return
    labels = {}
    records = frame.drop_duplicates("source_url").set_index("source_url", drop=False)
    for i, url in enumerate(options, 1):
        row = records.loc[url]
        title = readable(row.get("content_title")) or readable(row.get("source_author"))
        title = title or "Untitled source"
        platform = readable(row.get("source_platform")) or "Source unavailable"
        labels[url] = f"{i}. {title[:100]} · {platform}"
    selected = st.selectbox("Read source record", options, format_func=labels.get, key=key)
    row = records.loc[selected]
    render_record_details(row)
    from laclaugpt_visualization.provenance import provenance_frame, safe_provenance_events

    with st.expander("Safe provenance (technical details)"):
        st.json(safe_provenance_events(row))
        projected = provenance_frame(pd.DataFrame([row])).to_dict(orient="records")
        if projected:
            st.json(projected[0])
    return row


def render_record_details(row: Mapping):
    import streamlit as st

    st.markdown("##### Source evidence")
    # Render untrusted source content as literal text, not markup.
    source = readable(row.get("source_url"))
    if source:
        st.text(source)
        if url := source_link(source):
            st.markdown(f"[Open original source]({url})")
    for field, label in (
        ("human_readable_summary", "Researcher-readable summary"),
        ("summary", "Analysis summary"),
        ("source_text", "Source text"),
        ("caption", "Source caption"),
        ("translated_text", "Translation"),
        ("transcript", "Transcript"),
        ("whisper_transcript", "Legacy transcript"),
        ("ocr", "Text visible in media"),
    ):
        if content := readable(row.get(field)):
            if field == "whisper_transcript" and content == readable(row.get("transcript")):
                continue
            with st.expander(label, expanded=field in {"human_readable_summary", "summary"}):
                st.text(content)
    st.markdown("##### Analysis and review")
    st.caption(
        "Analytical coding is provisional unless explicitly reviewed. "
        "Missing output is not evidence of absence."
    )
    for key in ("analysis_status", "review_status"):
        status = readable(row.get(key)) or "Unavailable"
        st.text(f"{key.replace('_', ' ').capitalize()}: {status}")
    for field, label in DETAIL_FIELDS.items():
        if content := readable(row.get(field)):
            with st.expander(label):
                st.text(content)

def render_distribution(frame: pd.DataFrame, table: pd.DataFrame, field: str, title: str):
    """Selectable chart plus an accessible text control and evidence drill-down."""
    import plotly.express as px
    import streamlit as st

    if table.empty:
        st.info(f"No {title.lower()} in the current filtered window.")
        return
    shown = table.head(15).iloc[::-1]
    fig = px.bar(
        shown, x="count", y=field, orientation="h", text="count",
        labels={"count": "Label occurrences", field: title},
    )
    chart_style(fig).update_layout(height=max(300, 130 + 30 * len(shown)))
    fig.update_traces(textposition="outside", cliponaxis=False)
    event = st.plotly_chart(
        fig, width="stretch", on_select="rerun", selection_mode="points",
        key=f"ai26_distribution_{field}",
    )
    st.caption(
        f"Top {len(shown)} of {len(table)} labels in the filtered view. "
        "Multilabel occurrences can exceed the number of records."
    )
    options = table[field].tolist()
    selected_points = event.selection.points
    picked = selected_points[0].get("y") if selected_points else None
    manual = st.selectbox(
        f"Inspect {title.lower()} label", options, index=None,
        key=f"ai26_distribution_label_{field}",
        help="Select a label here or click its chart bar; clear this control to follow the chart.",
    )
    label = manual if manual is not None else (picked if picked in options else None)
    if label is not None:
        sources = table.loc[table[field].eq(label), "source_urls"].iloc[0]
        render_evidence(frame, sources, f"ai26_distribution_record_{field}")
