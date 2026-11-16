"""Legacy EP24 reading-workbench parity on reprocessed records.

Read-only: never writes annotations or infers missing analytical classifications.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from laclaugpt_visualization.ep24_presentation import hydrate_record, readable
from laclaugpt_visualization.ep24_reprocessed import identity, text

# Explicit one-to-one legacy surface inventory; missing producers are deliberate.
RECORD_TABS = (
    "Metadata", "Whisper", "OCR", "Multimodal", "Summary",
    "Populism", "Themes", "Persons", "Report Problems / Researcher Notes",
)
AGGREGATE_TABS = (
    "Frequency", "Entities", "Topics", "Sentiments", "Languages",
    "ManifestoBERTa", "Statistics", "Themes", "Persons",
)
NO_SOURCE = {
    "Topics": "No LDA topic classifications are produced by the reprocessed pipeline.",
    "ManifestoBERTa": "No ManifestoBERTa predicted classes are in the export.",
}
RECORD_FIELDS = {
    "Metadata": ("country", "source_type", "account_type", "source_url", "title",
                 "author_username", "political_preference", "created_at",
                 "source_recording", "video_duration", "duration_seconds"),
    "Whisper": ("asr_transcript", "asr_translation"),
    "OCR": ("ocr_1",),
    "Multimodal": ("frame_analysis_1", "vllm_video_analysis"),
    "Summary": ("summary_analysis", "summary_summary_md"),
    "Populism": ("formula_of_populism_analysis", "formula_of_populism_analysis_us",
                 "formula_of_populism_analysis_frontier", "laclau_summary_md",
                 "laclau_structured_json"),
    "Themes": ("postprocess_themes",),
    "Persons": ("postprocess_entities",),
    "Report Problems / Researcher Notes": ("researcher_note",),
}


def available_aggregates(frame: pd.DataFrame) -> tuple[str, ...]:
    """Never show a legacy analytical tab without its producer field."""
    result = []
    for name in AGGREGATE_TABS:
        if name in NO_SOURCE:
            continue
        if name == "Sentiments" and not any(x in frame for x in ("positive", "neutral", "negative")):
            continue
        if name == "Languages" and not any(x in frame for x in ("source_language", "language")):
            continue
        if name in ("Entities", "Persons") and not any(x in frame for x in ("postprocess_entities", "entities")):
            # Child-table evidence can still provide these on real exports.
            result.append(name)
            continue
        if name == "Themes" and not any(x in frame for x in ("postprocess_themes", "themes")):
            result.append(name)
            continue
        result.append(name)
    return tuple(result)


def child_labels(root: str | Path, row: dict, kind: str) -> list[str]:
    """Join normalized children to one video; ambiguous IDs must not be assigned."""
    root = Path(root)
    country = text(row.get("country")).casefold()
    aliases = {"fi": "finland", "pl": "poland", "pt": "portugal"}
    country = aliases.get(country, country)
    source_id = text(row.get("_storage_id")) or text(row.get("source_record_id"))
    if not source_id:
        return []
    # The exporter uses either country/children/*.csv or root/children/<country>_*.csv.
    candidates = (
        root / country / "children" / f"{kind}.csv",
        root / country / "children" / f"{country}_{kind}.csv",
        root / "children" / f"{country}_{kind}.csv",
    )
    labels: set[str] = set()
    for path in candidates:
        if not path.is_file():
            continue
        try:
            table = pd.read_csv(path, dtype=str, keep_default_na=False)
        except (OSError, ValueError, pd.errors.ParserError):
            continue
        key = next((k for k in ("source_record_id", "_storage_id")
                    if k in table.columns), None)
        if key is None:
            continue
        subset = table.loc[table[key] == source_id]
        for field in ("name", "label", "entity", "theme", "person", "value"):
            if field in subset:
                labels.update(text(x) for x in subset[field] if text(x))
                break
    return sorted(labels)



def child_frequencies(root: str | Path, frame: pd.DataFrame, kind: str
                      ) -> pd.DataFrame:
    """Count distinct matched videos by exported child label, without guessing IDs.

    The count unit is a video, not a child row. Cross-country source IDs are
    namespaced and ambiguous parent IDs are excluded rather than attributed.
    """
    root = Path(root)
    aliases = {"fi": "finland", "pl": "poland", "pt": "portugal"}
    parents: dict[tuple[str, str], set[int]] = {}
    for index, row in enumerate(frame.to_dict("records")):
        country = aliases.get(text(row.get("country")).casefold(),
                              text(row.get("country")).casefold())
        for field in ("_storage_id", "source_record_id"):
            source = text(row.get(field))
            if source:
                parents.setdefault((country, source), set()).add(index)

    counts: dict[str, set[int]] = {}
    for country in sorted({name for name, _ in parents}):
        paths = (root / country / "children" / f"{kind}.csv",
                 root / country / "children" / f"{country}_{kind}.csv",
                 root / "children" / f"{country}_{kind}.csv")
        path = next((p for p in paths if p.is_file()), None)
        if path is None:
            continue
        try:
            children = pd.read_csv(path, dtype=str, keep_default_na=False)
        except (OSError, ValueError, pd.errors.ParserError):
            continue
        field = next((k for k in ("name", "label", "entity", "theme", "person", "value")
                      if k in children.columns), None)
        if field is None:
            continue
        for child in children.to_dict("records"):
            matches: set[int] = set()
            for key in ("source_record_id", "_storage_id"):
                identifier = text(child.get(key))
                if identifier:
                    matches.update(parents.get((country, identifier), set()))
            label = text(child.get(field)).strip()
            if label and len(matches) == 1:
                counts.setdefault(label, set()).update(matches)
    return pd.DataFrame(
        [{"label": label, "videos": len(indices)}
         for label, indices in counts.items()]
    ).sort_values(["videos", "label"], ascending=[False, True]).reset_index(
        drop=True
    ) if counts else pd.DataFrame(columns=["label", "videos"])


def render_record(root: str | Path, row: dict) -> None:
    """All nine legacy per-record surfaces, without pretending edits are saved."""
    import streamlit as st

    if not row:
        st.info("Choose a record with a stable source identifier.")
        return
    row = hydrate_record(root, row)
    st.caption("Record identity (dataset | country | source | native ID): " + identity(row))
    tabs = st.tabs(RECORD_TABS)
    for name, tab in zip(RECORD_TABS, tabs):
        with tab:
            fields = RECORD_FIELDS[name]
            shown = False
            for field in fields:
                value = readable(row.get(field))
                if value:
                    st.markdown("**" + field.replace("_", " ").capitalize() + "**")
                    st.text(value)
                    shown = True
            if name in ("Themes", "Persons"):
                child_kind = "themes" if name == "Themes" else "entities"
                children = child_labels(root, row, child_kind)
                if children:
                    st.caption("Normalized child table; linked by exported source record ID")
                    st.write(children)
                    shown = True
            if name == "Report Problems / Researcher Notes":
                st.warning("Read-only view: review decisions, edits, split/cut requests and rerun flags "
                           "are not saved here. Do not treat displayed annotations as a write-back.")
            if not shown:
                st.info("No exported source for this record and tab.")
    st.caption("The existing evidence inspector remains available below these tabs.")


def _count_chart(frame: pd.DataFrame, field: str, label: str) -> None:
    import streamlit as st

    if field not in frame:
        st.info(f"{label}: source field absent")
        return
    values = frame[field].fillna("").astype(str).replace("", "Unavailable")
    st.bar_chart(values.value_counts().rename("Videos"))
    st.caption(f"{label}: denominator {len(frame)} filtered rows; one video row counted once. "
               "Missing values are explicitly shown as unavailable.")


def render_aggregates(root: str | Path, frame: pd.DataFrame) -> None:
    """Descriptive legacy aggregates; never synthesize LDA/ManifestoBERTa results."""
    import streamlit as st

    st.subheader("Legacy corpus aggregates")
    st.caption(f"Denominator: {len(frame)} filtered video rows. Identity: exported row, "
               "not unique author, claim or inferred entity. Categories may overlap.")
    tabs = available_aggregates(frame)
    for name, tab in zip(tabs, st.tabs(tabs)):
        with tab:
            if name == "Frequency":
                _count_chart(frame, "political_preference", "Political preference")
                if "video_duration" in frame or "duration_seconds" in frame:
                    duration = next(c for c in ("duration_seconds", "video_duration")
                                    if c in frame)
                    numeric = pd.to_numeric(frame[duration], errors="coerce")
                    st.caption(f"Duration: {int(numeric.notna().sum())} of {len(frame)} rows "
                               "have numeric seconds; unavailable values excluded.")
                    if "political_preference" in frame:
                        durations = pd.DataFrame({
                            "Preference": frame["political_preference"].fillna("Unavailable"),
                            "Seconds": numeric,
                        }).groupby("Preference")["Seconds"].sum(min_count=1).dropna()
                        if not durations.empty:
                            st.bar_chart(durations)
            elif name == "Statistics":
                for field in ("country", "source_type", "account_type", "political_preference"):
                    _count_chart(frame, field, field.replace("_", " ").capitalize())
                if {"country", "political_preference"} <= set(frame):
                    st.dataframe(pd.crosstab(frame["country"], frame["political_preference"]))
            elif name == "Languages":
                field = next((c for c in ("source_language", "language") if c in frame), None)
                if field:
                    _count_chart(frame, field, "Exported source language (not Whisper unless specified)")
            elif name == "Sentiments":
                cols = [c for c in ("positive", "neutral", "negative") if c in frame]
                counts = {c: int(pd.to_numeric(frame[c], errors="coerce").notna().sum())
                          for c in cols}
                st.bar_chart(pd.Series(counts, name="Rows with available sentiment field"))
                st.caption("Availability counts, not sentiment class predictions; "
                           "scores are not converted into classes.")
            else:
                kind = "themes" if name == "Themes" else "entities"
                frequencies = child_frequencies(root, frame, kind)
                if not frequencies.empty:
                    st.caption(f"Normalized {kind}: each label counts distinct matched videos; "
                               f"denominator {len(frame)} filtered video rows. "
                               "Ambiguous and orphan child records are excluded.")
                    st.dataframe(frequencies.head(100), use_container_width=True)
                    st.bar_chart(frequencies.head(30).set_index("label")["videos"])
                field = "postprocess_themes" if name == "Themes" else "postprocess_entities"
                if field in frame:
                    present = frame[field].map(lambda v: bool(text(v)))
                    st.metric("Videos with row-level " + name.lower(), int(present.sum()))
                    st.caption(f"Denominator {len(frame)} video rows; one row counted at most once. "
                               "Child-table detail is shown in the selected record.")
                else:
                    st.info("Row-level labels absent. Open a record for normalized child-table labels.")
