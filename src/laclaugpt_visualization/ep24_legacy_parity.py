"""Legacy-parity view model for the EP24 dashboard (#263).

The legacy dashboard at `:8501` is a curation workbench: eleven sidebar filters, a nine-tab per-record
reader and a nine-tab aggregate view. The reprocessed app at `:8502` answers a different question — "what did
the pipeline do, and where is its evidence" — so "make it exactly like the legacy one" cannot be satisfied by
restyling. This module is the part that *can* be shared with a test: which legacy tabs exist, which new
column feeds each one, and which ones have no source at all in the reprocessed export.

Two rules keep it honest:

* **A tab with no source is declared, not rendered empty.** `manifestoberta_predicted_class` and `lda_topic`
  were produced by the legacy pipeline and by nothing in the current one; a researcher who sees an empty chart
  learns nothing, and an agent who sees one assumes a bug.
* **Every count names its denominator.** The repository's existing rule (#205): two exports legitimately
  disagree on totals, so a "records" figure without its identity rule and its filter scope is not a claim.

Read-only by design: the legacy write path (review flags, cut/split, notes to MongoDB) is deliberately not
implemented here. Where a researcher's decision lands is the open decision in #263 §4, and inventing a second
write path would be worse than leaving the workbench read-only for one increment.
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from laclaugpt_visualization.ep24_presentation import readable

#: Per-record tabs of the legacy dashboard (`dashboard.py:637-760`), in legacy order.
RECORD_TABS = (
    "Metadata",
    "Whisper",
    "OCR",
    "Multimodal",
    "Summary",
    "Populism",
    "Themes",
    "Persons",
    "Report Problems / Researcher Notes",
)

#: Aggregate tabs of the legacy dashboard (`dashboard.py:768-1132`), in legacy order.
AGGREGATE_TABS = (
    "Frequency",
    "Entities",
    "Topics",
    "Sentiments",
    "Languages",
    "ManifestoBERTa",
    "Statistics",
    "Themes",
    "Persons",
)

#: Where each legacy tab's content comes from in the reprocessed export. A value of ``None`` means the
#: legacy pipeline produced the column and the current one does not — the tab is declared unsupported rather
#: than rendered empty, with the reason string a person can act on.
RECORD_SOURCES: dict[str, tuple[str, ...] | None] = {
    "Metadata": ("video_id", "country", "source_type", "account_type", "political_preference",
                 "timestamp", "video_duration_seconds"),
    "Whisper": ("asr_transcript", "asr_translation"),
    "OCR": ("ocr_1",),
    "Multimodal": ("frame_analysis_1", "vllm_video_analysis"),
    "Summary": ("summary_analysis", "summary_summary_md"),
    "Populism": ("formula_of_populism_analysis", "formula_of_populism_us",
                 "formula_of_populism_frontier", "laclau_abstention_reason"),
    "Themes": ("__child__:postprocess_themes",),
    "Persons": ("__child__:postprocess_entities",),
    "Report Problems / Researcher Notes": ("researcher_note",),
}

AGGREGATE_SOURCES: dict[str, tuple[str, ...] | None] = {
    "Frequency": ("timestamp", "political_preference", "video_duration_seconds"),
    "Entities": ("__child__:postprocess_entities",),
    "Topics": None,
    "Sentiments": ("positive", "neutral", "negative"),
    "Languages": ("asr_language",),
    "ManifestoBERTa": None,
    "Statistics": ("country", "political_preference", "source_type"),
    "Themes": ("__child__:postprocess_themes",),
    "Persons": ("__child__:postprocess_entities",),
}

#: Why a tab has no source. Kept next to the registry so the reason travels with the decision.
NO_SOURCE_REASON = {
    "Topics": (
        "LDA topics (`lda_topic`) were produced by the legacy preprocessing and are not part of the "
        "reprocessed export; reproducing the tab needs an LDA step, which is an analysis decision, not a "
        "dashboard change."
    ),
    "ManifestoBERTa": (
        "`manifestoberta_predicted_class` came from the legacy ManifestoBERTa stage and has no counterpart "
        "in the reprocessed pipeline; the tab and its sidebar filter are therefore unavailable."
    ),
}

#: Legacy sidebar filters that have a reprocessed source, with the column they filter on.
FILTERS: dict[str, str] = {
    "Country": "country",
    "Political preference": "political_preference",
    "Source type": "source_type",
    "Language": "asr_language",
    "Duration": "video_duration_seconds",
    "Date": "timestamp",
}

#: Legacy filters with no reprocessed source (the legacy workbench could filter on these).
UNSUPPORTED_FILTERS = ("ManifestoBERTa class", "LDA topic", "Whisper model-free entity filter")

PLATFORM_DERIVATION = "Platform is represented by the exported source_type and account_type fields; no legacy platform class is inferred."


def label_for(column: str) -> str:
    """Human-readable label for a field already approved for display."""
    names = {"asr_transcript": "Transcript (original)", "asr_translation": "Translation"}
    return names.get(column, column.replace("_", " ").strip().capitalize())



@dataclass(frozen=True)
class Parity:
    """The answer to "is the legacy tab available, and if not, why"."""

    tab: str
    kind: str
    columns: tuple[str, ...]
    available: bool
    reason: str = ""

    def as_row(self) -> dict[str, Any]:
        return {
            "tab": self.tab,
            "view": self.kind,
            "source": ", ".join(self.columns) if self.columns else "—",
            "available": "yes" if self.available else "no",
            "note": self.reason,
        }


def parity_rows() -> list[dict[str, Any]]:
    """Every legacy tab, in legacy order, with its source and its availability."""
    rows: list[dict[str, Any]] = []
    for kind, tabs, sources in (
        ("per-record", RECORD_TABS, RECORD_SOURCES),
        ("aggregate", AGGREGATE_TABS, AGGREGATE_SOURCES),
    ):
        for tab in tabs:
            columns = sources.get(tab)
            available = columns is not None
            rows.append(
                Parity(
                    tab=tab,
                    kind=kind,
                    columns=tuple(columns or ()),
                    available=available,
                    reason=("" if available else NO_SOURCE_REASON.get(tab, "no source in the reprocessed export")),
                ).as_row()
            )
    return rows


def unsupported_tabs() -> list[str]:
    return [row["tab"] for row in parity_rows() if row["available"] == "no"]


def _child_values(children: pd.DataFrame | None, row: Mapping[str, Any], field: str) -> list[str]:
    """Entities or themes for one record, from the export's child tables."""
    if children is None or children.empty:
        return []
    matches = children[children["field"] == field] if "field" in children.columns else children
    if "source_key" in children.columns:
        key = str(row.get("source_key") or "").strip()
        matches = matches[matches["source_key"].astype(str).str.strip() == key] if key else matches.iloc[0:0]
    elif "parent_record_id" in children.columns:
        identifier = str(row.get("record_id") or "").strip()
        matches = (matches[matches["parent_record_id"].astype(str).str.strip() == identifier]
                   if identifier else matches.iloc[0:0])
    else:
        return []
    if "country" in matches and row.get("country"):
        matches = matches[matches["country"].astype(str).str.casefold() == str(row["country"]).casefold()]
    if matches.empty:
        return []
    ordered = matches.sort_values("index") if "index" in matches.columns else matches
    return [str(value) for value in ordered["item.label"].dropna()]


def record_tabs(row: Mapping[str, Any], children: pd.DataFrame | None = None) -> dict[str, dict[str, Any]]:
    """The content of each per-record tab for one record, as labelled text blocks.

    Returns ``{tab: {"available", "blocks", "absent", "empty", "note", "reason"}}``. The four states stay
    apart on purpose, because collapsing them is how a tab lies:

    ``blocks``   what this record actually carries, already projected through the display allowlist;
    ``absent``   source columns the export does not carry at all (a data defect, named);
    ``empty``    columns the export carries but this record has no output for (an absence of output, not
                 a finding that the video has none);
    ``reason``   set only when the pipeline produces nothing for the tab at all.
    """
    tabs: dict[str, dict[str, Any]] = {}
    for tab in RECORD_TABS:
        columns = RECORD_SOURCES.get(tab)
        if columns is None:
            tabs[tab] = {"available": False, "content": "", "reason": NO_SOURCE_REASON.get(tab, "")}
            continue
        if columns == ("__child__:postprocess_themes",):
            values = _child_values(children, row, "postprocess_themes")
            tabs[tab] = {"available": True,
                         "blocks": ([{"label": tab, "value": ", ".join(values)}] if values else []),
                         "absent": [], "empty": ([] if values else [tab]),
                         "note": "", "reason": ""}
            continue
        if columns == ("__child__:postprocess_entities",):
            values = _child_values(children, row, "postprocess_entities")
            tabs[tab] = {"available": True,
                         "blocks": ([{"label": tab, "value": ", ".join(values)}] if values else []),
                         "absent": [], "empty": ([] if values else [tab]),
                         "note": "", "reason": ""}
            continue

        blocks: list[dict[str, str]] = []
        absent: list[str] = []
        empty: list[str] = []
        if tab == "Metadata" and "platform" not in row:
            # Only say it once, and only when the export does not carry the legacy column.
            blocks.append({"label": "Platform (derived)", "value": PLATFORM_DERIVATION})
        for column in columns:
            if column not in row:
                absent.append(label_for(column))
                continue
            value = readable(row.get(column))
            if not value:
                empty.append(label_for(column))
                continue
            blocks.append({"label": label_for(column), "value": value})
        tabs[tab] = {"available": True, "blocks": blocks, "absent": absent, "empty": empty,
                     "note": "", "reason": ""}
    return tabs


def apply_filters(
    frame: pd.DataFrame,
    *,
    countries: Sequence[str] = (),
    political_preferences: Sequence[str] = (),
    source_types: Sequence[str] = (),
    languages: Sequence[str] = (),
    duration: tuple[float, float] | None = None,
    dates: tuple[Any, Any] | None = None,
    search: str = "",
    search_column: str = "",
) -> pd.DataFrame:
    """The legacy sidebar's filters, applied without inventing state.

    An empty selection means "no restriction" for every multiselect, matching the legacy behaviour; the
    search box is case-insensitive and only applies when a column is named, because searching every column
    would silently match identifiers and mislead.
    """
    data = frame
    for column, selected in (
        ("country", countries),
        ("political_preference", political_preferences),
        ("source_type", source_types),
        ("asr_language", languages),
    ):
        if selected and column in data.columns:
            wanted = {str(value).casefold() for value in selected}
            data = data[data[column].astype(str).str.casefold().isin(wanted)]
    if duration and "video_duration_seconds" in data.columns:
        low, high = duration
        numeric = pd.to_numeric(data["video_duration_seconds"], errors="coerce")
        data = data[(numeric >= low) & (numeric <= high)]
    if dates and "timestamp" in data.columns:
        parsed = pd.to_datetime(data["timestamp"], errors="coerce", utc=True)
        start = pd.Timestamp(dates[0], tz="UTC") if dates[0] is not None else parsed.min()
        # A date input gives midnight, so a naive filter silently drops the whole end day. Build the end
        # boundary with stdlib datetime rather than pandas timedelta arithmetic, which warns on this version.
        if dates[1] is not None:
            last_day = pd.Timestamp(dates[1]).date()
            end = pd.Timestamp(datetime.datetime.combine(last_day, datetime.time.max), tz="UTC")
        else:
            end = parsed.max()
        if pd.notna(start) and pd.notna(end):
            data = data[(parsed >= start) & (parsed <= end)]
    if search and search_column and search_column in data.columns:
        data = data[data[search_column].astype(str).str.contains(search, case=False, na=False, regex=False)]
    return data


def frequency_by(data: pd.DataFrame, group: str = "political_preference") -> pd.DataFrame:
    """Record counts by a grouping column — the denominator is always the filtered frame."""
    if group not in data.columns:
        return pd.DataFrame(columns=[group, "records"])
    counts = data[group].fillna("(unknown)").astype(str).value_counts()
    return pd.DataFrame({group: counts.index, "records": counts.values})


def duration_by(data: pd.DataFrame, group: str = "political_preference") -> pd.DataFrame:
    """Total video duration by a grouping column, in minutes, with the record count beside it."""
    if not {"video_duration_seconds", group} <= set(data.columns):
        return pd.DataFrame(columns=[group, "minutes", "records"])
    frame = data.assign(
        _seconds=pd.to_numeric(data["video_duration_seconds"], errors="coerce"),
        _group=data[group].fillna("(unknown)").astype(str),
    )
    grouped = frame.groupby("_group").agg(minutes=("_seconds", "sum"), records=("_seconds", "size"))
    grouped["minutes"] = (grouped["minutes"] / 60).round(1)
    return grouped.reset_index().rename(columns={"_group": group}).sort_values("minutes", ascending=False)


def sentiment_counts(data: pd.DataFrame) -> pd.DataFrame:
    """Positive/neutral/negative totals — the legacy Sentiments tab, minus its per-term breakdown."""
    columns = [column for column in ("positive", "neutral", "negative") if column in data.columns]
    if not columns:
        return pd.DataFrame(columns=["sentiment", "records"])
    rows = [{"sentiment": column, "records": int(pd.to_numeric(data[column], errors="coerce").gt(0).sum())}
            for column in columns]
    return pd.DataFrame(rows)


def language_counts(data: pd.DataFrame) -> pd.DataFrame:
    if "asr_language" not in data.columns:
        return pd.DataFrame(columns=["language", "records"])
    counts = data["asr_language"].fillna("(unknown)").astype(str).value_counts()
    return pd.DataFrame({"language": counts.index, "records": counts.values})



def scope_children(children: pd.DataFrame | None, parents: pd.DataFrame) -> pd.DataFrame:
    """Join children only to uniquely identified filtered parents."""
    if children is None or children.empty or "source_key" not in children:
        return pd.DataFrame(columns=list(children.columns) if children is not None else [])
    if "source_key" not in parents or parents.empty:
        return children.iloc[0:0].copy()
    parent = parents[["source_key"] + (["country"] if "country" in parents else [])].copy()
    parent["source_key"] = parent["source_key"].astype(str)
    incoming = children.copy()
    incoming["source_key"] = incoming["source_key"].astype(str)
    if "country" in incoming and "country" in parent:
        keys = ["source_key", "country"]
        parent["country"] = parent["country"].astype(str).str.casefold()
        incoming["country"] = incoming["country"].astype(str).str.casefold()
    else:
        keys = ["source_key"]
    unique = parent.loc[~parent.duplicated(keys, keep=False), keys]
    return incoming.merge(unique, on=keys, how="inner", validate="many_to_one")


def child_counts(children: pd.DataFrame | None, field: str, *, limit: int = 20) -> pd.DataFrame:
    """Top entities or themes across the filtered records."""
    if children is None or children.empty or not {"field", "item.label", "source_key"} <= set(children.columns):
        return pd.DataFrame(columns=["label", "videos"])
    subset = children[children["field"] == field]
    if subset.empty:
        return pd.DataFrame(columns=["label", "records"])
    counts = (subset.dropna(subset=["item.label", "source_key"])
              .drop_duplicates(["source_key", "item.label"] + (["country"] if "country" in subset else []))["item.label"]
              .astype(str).value_counts().head(limit))
    return pd.DataFrame({"label": counts.index, "videos": counts.values})


def child_counts_over_time(children: pd.DataFrame | None, parents: pd.DataFrame,
                           field: str, *, limit: int = 8) -> pd.DataFrame:
    """Label counts by month, for the legacy "Themes/Persons over time" charts.

    Counted once per (video, label, month) for the same reason as :func:`child_counts`.
    """
    empty = pd.DataFrame(columns=["month", "label", "videos"])
    if children is None or children.empty or not {"source_key", "field", "item.label"} <= set(children.columns):
        return empty
    if not {"source_key", "timestamp"} <= set(parents.columns):
        return empty
    join_keys = ["source_key"]
    if "country" in children and "country" in parents:
        join_keys.append("country")
    dates = parents[join_keys + ["timestamp"]].copy()
    dates["month"] = pd.to_datetime(dates["timestamp"], errors="coerce", utc=True).dt.tz_localize(None).dt.to_period("M")
    dates = dates.dropna(subset=["month"])
    if dates.empty:
        return empty
    subset_fields = ["source_key", "item.label"]
    if "country" in children:
        subset_fields.append("country")
    subset = children[children["field"] == field][subset_fields].drop_duplicates()
    merged = subset.merge(dates[join_keys + ["month"]], on=join_keys, how="inner", validate="many_to_one")
    if merged.empty:
        return empty
    top = merged["item.label"].astype(str).value_counts().head(limit).index
    merged = merged[merged["item.label"].astype(str).isin(top)]
    grouped = (merged.groupby([merged["month"].astype(str), merged["item.label"].astype(str)])
               .size().reset_index(name="videos"))
    return grouped.rename(columns={"level_0": "month", "level_1": "label"})


def load_children(root: str | Any, parents: pd.DataFrame) -> pd.DataFrame:
    """Read the export's child tables (entities, themes) as one frame, or an empty frame.

    The flat layout keeps them at the export root; the per-country layout keeps them in ``children/``.
    Both are accepted because #263 asks for one layout *eventually*, and a loader that only reads the one
    currently deployed would hide the difference until the migration happens.
    """
    from pathlib import Path

    base = Path(root)
    frames: list[pd.DataFrame] = []
    candidates = [
        base / "children",
        *(base / country / "children" for country in ("finland", "poland", "portugal")),
        base,
    ]
    seen: set[Path] = set()
    for folder in candidates:
        if not folder.is_dir():
            continue
        for name in ("entities.csv", "themes.csv"):
            path = folder / name
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            try:
                data = pd.read_csv(path, low_memory=False)
                if folder.parent.name in ("finland", "poland", "portugal") and "country" not in data:
                    data["country"] = folder.parent.name
                frames.append(data)
            except (OSError, pd.errors.ParserError):
                continue
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    if "child_id" in merged.columns:
        merged = merged.drop_duplicates(subset=["child_id"])
    return merged
