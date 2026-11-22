"""Researcher-reading parity with the legacy EP24 dashboard (#263).

The legacy dashboard at `:8501` is a curation workbench; `:8502` is a pipeline-evidence
explorer. #263 asks for the *reading* half of the legacy experience on the new data,
leaving the write path alone until the owner picks where a decision lands (§4 of the
issue, whose recommendation is (c) first, then (b)).

So this module is deliberately pure and side-effect free: it maps every legacy tab to the
new export's columns, or declares it absent with a reason, and it computes aggregate
tables that state their denominator and identity rule. That makes the parity claim
testable without a browser, which is what acceptance criterion 5 asks for.

Three rules encoded here, each of which the legacy dashboard silently got away with:

* **A tab with no source column is absent, never empty.** `Topics` (no `lda_topic`) and
  `ManifestoBERTa` (no `manifestoberta_predicted_class`) cannot be reproduced, and an
  empty chart would read as "the phenomenon is missing".
* **Every chart names its denominator**, because two exports legitimately disagree on
  totals and "1,500 videos" is not a denominator for a count that excludes blanks.
* **Every chart names its identity rule**, so a record counted twice or a record with no
  stable id is visible rather than averaged away.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TabParity:
    """One legacy tab and what the new export can do with it."""

    legacy_tab: str
    status: str  # "mapped" | "absent"
    source: tuple[str, ...] = ()
    reason: str = ""


#: Legacy per-record tabs (§1.2). Each maps to new-export columns; `Themes` and `Persons`
#: are child tables upstream but are also exported as row columns by the reprocessor, and
#: the first match wins so a bundle with only child tables still declares them.
RECORD_TABS: Mapping[str, tuple[str, ...]] = {
    "Metadata": ("country", "source_type", "account_type", "political_preference",
                 "video_duration_seconds", "video_duration"),
    "Whisper transcript": ("asr_transcript",),
    "Whisper translation": ("asr_translation",),
    "OCR (frame 1)": ("ocr_1",),
    "Multimodal (frame 1)": ("frame_analysis_1", "vllm_video_analysis"),
    "Summary": ("summary_analysis", "summary_summary_md"),
    "Populism": ("formula_of_populism_analysis", "formula_of_populism_us",
                 "formula_of_populism_frontier"),
    "Themes": ("postprocess_themes",),
    "Persons": ("postprocess_entities",),
    "Report problems / Researcher notes": ("researcher_note",),
}

#: Legacy aggregate tabs (§1.3), with the columns each counts.
AGGREGATE_TABS: Mapping[str, tuple[str, ...]] = {
    "Frequency": ("country", "source_type"),
    "Entities": ("postprocess_entities",),
    "Sentiments": ("positive", "neutral", "negative"),
    "Languages": ("source_language", "language"),
    "Statistics": ("political_preference", "source_type"),
    "Themes": ("postprocess_themes",),
    "Persons": ("postprocess_entities",),
}

#: Tabs the new pipeline cannot reproduce, with the missing source named.
ABSENT_TABS: Mapping[str, str] = {
    "Topics": "no `lda_topic` column or child table in the reprocessed export",
    "ManifestoBERTa": "no `manifestoberta_predicted_class` column; the stage is not in the pipeline",
}

#: Legacy `platform` is derived, and the derivation changes what the chart means.
PLATFORM_MAPPING = "platform is derived from source_type + account_type; the legacy column does not exist"

#: The date filter must name its column, because the export carries several.
DATE_FIELDS = ("created_at", "published_at", "recorded_at", "timestamp", "source_recording")


def _present(columns: Iterable[str]) -> set[str]:
    return {str(column) for column in columns}


def record_tab_parity(columns: Iterable[str]) -> list[TabParity]:
    """Per-record tabs, mapped or absent. Child-table-only exports keep Themes/Persons mapped."""
    present = _present(columns)
    result: list[TabParity] = []
    for tab, sources in RECORD_TABS.items():
        hit = tuple(column for column in sources if column in present)
        result.append(TabParity(tab, "mapped", hit) if hit
                      else TabParity(tab, "absent", (), "no source column in this export"))
    return result


def aggregate_tab_parity(columns: Iterable[str]) -> list[TabParity]:
    """Aggregate tabs, with the two unsourceable ones declared absent and reasoned."""
    present = _present(columns)
    result: list[TabParity] = []
    for tab, sources in AGGREGATE_TABS.items():
        hit = tuple(column for column in sources if column in present)
        if hit:
            result.append(TabParity(tab, "mapped", hit))
        else:
            result.append(TabParity(tab, "absent", (), "no source column in this export"))
    for tab, reason in ABSENT_TABS.items():
        result.append(TabParity(tab, "absent", (), reason))
    return result


def absent_tabs(columns: Iterable[str]) -> list[TabParity]:
    """Every tab that will not be rendered, so it can be documented rather than dropped."""
    return [tab for tab in (*record_tab_parity(columns), *aggregate_tab_parity(columns))
            if tab.status == "absent"]


def identity_rule(columns: Iterable[str], *, identity_column: str = "video_id") -> str:
    """Which column identifies a record, stated so a chart's counts can be audited."""
    present = _present(columns)
    if identity_column in present:
        return f"one record per `{identity_column}`; rows without it are counted as unidentified"
    return "one record per exported row; this export has no stable id column"


def counts(frame: pd.DataFrame, column: str, *, top: int | None = None) -> pd.DataFrame:
    """Value counts that state the denominator they are drawn from (#263 §5.3).

    An empty or missing column returns an empty frame with the reason in `.attrs`, so the
    caller can say "absent" instead of drawing an empty chart.
    """
    if column not in frame.columns:
        empty = pd.DataFrame(columns=["value", "records", "share"])
        empty.attrs["denominator"] = "column absent"
        return empty
    series = frame[column].fillna("(blank)").astype(str)
    denominator = len(series)
    tally = series.value_counts()
    if top is not None:
        tally = tally.head(top)
    table = pd.DataFrame({"value": tally.index, "records": tally.to_numpy()})
    table["share"] = (table["records"] / denominator).round(4) if denominator else 0.0
    table.attrs["denominator"] = (
        f"{denominator} rows carrying `{column}`, including blanks; not the corpus size"
    )
    table.attrs["identity_rule"] = identity_rule(frame.columns)
    return table


def denominator_caption(table: pd.DataFrame, column: str) -> str:
    """A one-line caption naming the denominator and identity rule for a chart."""
    return (f"`{column}` · denominator: {table.attrs.get('denominator', 'unknown')}"
            f" · identity: {table.attrs.get('identity_rule', 'unknown')}")


def legacy_tab_names() -> list[str]:
    """Every legacy tab across both tab sets, in issue order — the parity checklist."""
    return [*RECORD_TABS, *AGGREGATE_TABS, *ABSENT_TABS]


def record_values(row: Mapping[str, object], columns: Sequence[str]) -> dict[str, object]:
    """The verbatim field values for one record tab, skipping the ones this export lacks."""
    return {column: row[column] for column in columns if column in row}
