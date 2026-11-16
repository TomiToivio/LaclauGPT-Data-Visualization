"""Legacy-parity researcher workbench for the reprocessed EP24 export (#263).

The legacy ``:8501`` dashboard is not a viewer: a researcher opens one video, reads nine tabs of
evidence, and curates the record. This module rebuilds the **reading half** of that workbench on the
reprocessed FI/PL/PT export, and does it in a way that cannot quietly claim parity it does not have.

Two rules are enforced here rather than described:

* **Every legacy tab names its source.** Each tab in ``RECORD_TABS`` / ``AGGREGATE_TABS`` is mapped to
  the new-export columns or child table that feed it, or it is listed in ``NO_SOURCE`` with the reason.
  :func:`legacy_parity` returns that mapping as rows, and the test suite reads it — so "the tab is
  equivalent" is a checked claim, not a resemblance.
* **Unavailability is reported, never rendered as zero.** A tab whose fields are absent from this
  export says which fields it looked for; an empty tab that looks like "no findings" is the defect this
  module exists to prevent.

Write path (legacy wrote ``video_checked`` / ``delete_video`` / ``rerun_*`` / ``cut_video`` /
``split_video`` / ``new_persons`` / ``new_themes`` / ``researcher_note`` into MongoDB) is **not
implemented**: where a researcher's decision lands is issue #263 §4, an owner decision. The notes tab
therefore states the limitation on screen instead of showing a form that saves nothing.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from laclaugpt_visualization.ep24_presentation import readable

#: The legacy per-record tabs, in the order the workbench showed them (dashboard.py:637–760).
RECORD_TABS: tuple[tuple[str, str], ...] = (
    ("metadata", "Metadata"),
    ("whisper", "Whisper"),
    ("ocr", "OCR"),
    ("multimodal", "Multimodal"),
    ("summary", "Summary"),
    ("populism", "Populism"),
    ("themes", "Themes"),
    ("persons", "Persons"),
    ("notes", "Report Problems / Researcher Notes"),
)

#: The legacy aggregate tabs (dashboard.py:768–1132). Built in a later increment; specified here so the
#: parity table answers for all eighteen legacy tabs at once.
AGGREGATE_TABS: tuple[tuple[str, str], ...] = (
    ("frequency", "Frequency"),
    ("entities", "Entities"),
    ("topics", "Topics"),
    ("sentiments", "Sentiments"),
    ("languages", "Languages"),
    ("manifestoberta", "ManifestoBERTa"),
    ("statistics", "Statistics"),
    ("themes", "Themes"),
    ("persons", "Persons"),
)

#: Which new-export source feeds each record tab. ``child`` names the normalised child table that
#: carries one-to-many findings; the row columns are the fallback dialect for older exports.
RECORD_SOURCES: dict[str, dict[str, Any]] = {
    "metadata": {
        "columns": ("country", "source_type", "source_platform", "account_type",
                    "political_preference", "author_username", "title", "source_url",
                    "published_at", "source_recording", "created_at", "timestamp",
                    "video_duration_seconds", "duration_seconds", "video_duration",
                    "video_id", "dataset", "processing_status"),
        "child": None,
    },
    "whisper": {
        "columns": ("asr_transcript", "asr_translation", "asr_translated",
                    "whisper_transcript", "whisper_translation", "asr_language"),
        "child": None,
    },
    "ocr": {"columns": ("ocr_1",), "child": None},
    "multimodal": {
        "columns": ("frame_analysis_1", "vllm_video_analysis", "vllm_video_markdown_analysis"),
        "child": None,
    },
    "summary": {
        "columns": ("summary_analysis", "summary_summary_md", "postprocess_summary_md"),
        "child": None,
    },
    "populism": {
        "columns": ("formula_of_populism_analysis", "formula_of_populism_us",
                    "formula_of_populism_frontier", "laclau_summary_md"),
        "child": None,
    },
    "themes": {"columns": ("postprocess_themes", "themes"), "child": "themes"},
    "persons": {"columns": ("postprocess_entities", "entities"), "child": "entities"},
    "notes": {"columns": ("researcher_note",), "child": None},
}

AGGREGATE_SOURCES: dict[str, dict[str, Any]] = {
    "frequency": {"columns": ("country", "political_preference", "source_type",
                              "video_duration", "video_duration_seconds"), "child": None},
    "entities": {"columns": (), "child": "entities"},
    "topics": {"columns": (), "child": None},
    "sentiments": {"columns": ("positive", "neutral", "negative"), "child": "sentiment_targets"},
    "languages": {"columns": ("asr_language", "source_language", "language"), "child": None},
    "manifestoberta": {"columns": (), "child": None},
    "statistics": {"columns": ("country", "political_preference", "source_type"), "child": None},
    "themes": {"columns": (), "child": "themes"},
    "persons": {"columns": (), "child": "entities"},
}

#: Legacy tabs with **no source in the reprocessed pipeline at all**. Listed rather than rendered:
#: an empty chart reads as "the corpus contains none", which is a different claim.
NO_SOURCE: dict[tuple[str, str], str] = {
    ("aggregate", "topics"):
        "No `lda_topic` column: LDA topics were a legacy postprocess artefact and the reprocessed "
        "pipeline does not produce them. The Topics tab cannot be rebuilt from this export.",
    ("aggregate", "manifestoberta"):
        "No `manifestoberta_predicted_class` column: ManifestoBERTa is not run by the reprocessed "
        "pipeline. The ManifestoBERTa tab and its class filters have no source.",
}

#: Shown in the notes tab. The legacy workbench wrote review state; this build does not, and saying so
#: is better than rendering a form whose submit has nowhere to go.
NOTES_READ_ONLY = (
    "This build reads review state and does not write it. The legacy workbench recorded video_checked, "
    "delete_video, dubious_video, rerun_llm, rerun_ocr, rerun_whisper, cut_video/cut_at/cut_keep, "
    "split_video/split_at, new_persons, new_themes and researcher_note in MongoDB. Where a decision "
    "lands (MongoDB, an append-only review log in the private repository, or nothing yet) is issue "
    "#263 section 4 and is undecided, so no decision made here would be saved."
)

#: Legacy "platform" is derived, not stored: the new export has `source_type` (medium) and
#: `account_type` (who publishes). Stating the mapping changes what a platform chart means.
PLATFORM_DERIVATION = "platform = source_type + account_type (derived, not an exported column)"


def _first(row: Mapping[str, Any], names: Sequence[str]) -> tuple[str | None, str]:
    """First non-empty readable value among ``names``, with the column that supplied it."""
    for name in names:
        if name in row:
            rendered = readable(row.get(name))
            if rendered:
                return name, rendered
    return None, ""


def _child_labels(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    labels: list[str] = []
    for row in rows:
        label = readable(row.get("label")) or readable(row.get("name"))
        if label and label not in labels:
            labels.append(label)
    return labels


def children_for(children: Mapping[str, Sequence[Mapping[str, Any]]],
                 row: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The child rows belonging to one parent record, matched on the keys the dialects actually use."""
    source_key = str(row.get("source_key") or "").strip()
    record_id = str(row.get("record_id") or "").strip()
    selected: dict[str, list[dict[str, Any]]] = {}
    for name, items in children.items():
        selected[name] = [
            dict(item) for item in items
            if (source_key and str(item.get("source_key") or "").strip() == source_key)
            or (record_id and str(item.get("parent_record_id") or "").strip() == record_id)
        ]
    return selected


def _panel(key: str, label: str, blocks: list[dict[str, str]], *,
           missing: Sequence[str] = (), note: str = "") -> dict[str, Any]:
    return {"key": key, "label": label,
            "blocks": [block for block in blocks if block.get("value")],
            "missing": list(missing), "note": note}


def record_panels(row: Mapping[str, Any],
                  child_rows: Mapping[str, Sequence[Mapping[str, Any]]] | None = None
                  ) -> list[dict[str, Any]]:
    """The nine legacy per-record tabs as labelled text blocks, for one selected video.

    Values are read through :func:`readable`, so a structured cell is rendered as allowlisted text and
    never as a raw object dump. A tab with nothing to show keeps the names of the fields it looked for:
    that is the difference between "this export does not carry OCR here" and "the video has no text".
    """
    child_rows = child_rows or {}
    panels: list[dict[str, Any]] = []

    metadata_spec = (
        ("Country", ("country",)),
        ("Platform (derived)", ("source_type", "source_platform")),
        ("Account type", ("account_type",)),
        ("Political preference", ("political_preference",)),
        ("Creator", ("author_username",)),
        ("Title", ("title",)),
        ("Video link", ("source_url",)),
        ("Published", ("published_at",)),
        ("Recorded", ("source_recording",)),
        ("Created", ("created_at", "timestamp")),
        ("Duration (s)", ("video_duration_seconds", "duration_seconds", "video_duration")),
        ("Language", ("asr_language", "source_language", "language")),
        ("Video ID", ("video_id",)),
        ("Dataset", ("dataset",)),
        ("Processing status", ("processing_status",)),
        ("Summary quality", ("summary_quality_status",)),
    )
    metadata: list[dict[str, str]] = []
    if "platform" in row:
        # The legacy export carried `platform`; the reprocessed one derives it. Never present a
        # derivation as an observation.
        metadata.append({"label": "Platform", "value": readable(row.get("platform"))})
    else:
        metadata.append({"label": "Platform note", "value": PLATFORM_DERIVATION})
    metadata += [{"label": label, "value": _first(row, names)[1]} for label, names in metadata_spec]
    panels.append(_panel("metadata", "Metadata", metadata,
                         missing=[names[0] for _, names in metadata_spec
                                  if _first(row, names)[1] == ""][:6]))

    transcript = _first(row, ("asr_transcript", "whisper_transcript"))[1]
    translation = _first(row, ("asr_translation", "asr_translated", "whisper_translation"))[1]
    panels.append(_panel("whisper", "Whisper", [
        {"label": "Transcript (original)", "value": transcript},
        {"label": "Translation", "value": translation},
        {"label": "ASR language", "value": _first(row, ("asr_language",))[1]},
        {"label": "ASR model", "value": _first(row, ("asr_model", "asr_backend"))[1]},
    ], missing=[] if (transcript or translation) else
        ["asr_transcript", "asr_translation", "whisper_transcript", "whisper_translation"]))

    panels.append(_panel("ocr", "OCR", [
        {"label": "Text visible in frame 1", "value": _first(row, ("ocr_1",))[1]},
        {"label": "OCR model", "value": _first(row, ("ocr_model", "ocr_backend"))[1]},
    ], missing=[] if _first(row, ("ocr_1",))[1] else ["ocr_1"]))

    panels.append(_panel("multimodal", "Multimodal", [
        {"label": "Frame-1 interpretation", "value": _first(row, ("frame_analysis_1",))[1]},
        {"label": "Frame timestamp (s)", "value": _first(row, ("frame_timestamp_seconds",))[1]},
        {"label": "Whole-video observations", "value": _first(row, ("vllm_video_analysis",))[1]},
        {"label": "Temporal video interpretation",
         "value": _first(row, ("vllm_video_markdown_analysis",))[1]},
        {"label": "Model", "value": _first(row, ("frame_analysis_model", "vllm_video_model"))[1]},
    ], missing=[] if _first(row, ("frame_analysis_1", "vllm_video_analysis",
                                  "vllm_video_markdown_analysis"))[1]
        else ["frame_analysis_1", "vllm_video_analysis", "vllm_video_markdown_analysis"]))

    panels.append(_panel("summary", "Summary", [
        {"label": "Multimodal summary", "value": _first(row, ("summary_analysis",))[1]},
        {"label": "Summary", "value": _first(row, ("summary_summary_md",))[1]},
        {"label": "Postprocess interpretation", "value": _first(row, ("postprocess_summary_md",))[1]},
        {"label": "Quality status", "value": _first(row, ("summary_quality_status",))[1]},
        {"label": "Quality explanation", "value": _first(row, ("summary_quality_reason",))[1]},
    ], missing=[] if _first(row, ("summary_analysis", "summary_summary_md",
                                  "postprocess_summary_md"))[1]
        else ["summary_analysis", "summary_summary_md", "postprocess_summary_md"]))

    panels.append(_panel("populism", "Populism", [
        {"label": "Formula of populism", "value": _first(row, ("formula_of_populism_analysis",))[1]},
        {"label": "People / 'us' side", "value": _first(row, ("formula_of_populism_us",))[1]},
        {"label": "Frontier", "value": _first(row, ("formula_of_populism_frontier",))[1]},
        {"label": "Discourse interpretation", "value": _first(row, ("laclau_summary_md",))[1]},
        {"label": "Discourse availability", "value": _first(row, ("laclau_status",))[1]},
        {"label": "Discourse abstention", "value": _first(row, ("laclau_abstention_reason",))[1]},
    ], missing=[] if _first(row, ("formula_of_populism_analysis", "laclau_summary_md"))[1]
        else ["formula_of_populism_analysis", "laclau_summary_md"],
        note="Interpretation, not measurement: the formula of populism is a model output."))

    for key, label, child_name, column in (
            ("themes", "Themes", "themes", "postprocess_themes"),
            ("persons", "Persons", "entities", "postprocess_entities")):
        from_row = _first(row, (column, column.replace("postprocess_", "")))[1]
        labels = _child_labels(child_rows.get(child_name, []))
        blocks = []
        if from_row:
            blocks.append({"label": "Assignments in the record", "value": from_row})
        if labels:
            blocks.append({"label": f"{label} from the export's child table ({child_name}.csv)",
                           "value": "\n".join(f"• {item}" for item in labels)})
        panels.append(_panel(key, label, blocks,
                             missing=[] if (from_row or labels) else [column, f"{child_name}.csv"],
                             note="" if (from_row or labels) else
                             "No assignments for this record. That is an absence of output, not a "
                             "finding that the video has none."))

    note = _first(row, ("researcher_note",))[1]
    panels.append(_panel("notes", "Report Problems / Researcher Notes", [
        {"label": "Researcher annotation", "value": note},
        {"label": "Review state", "value": "unavailable" if not note else "one annotation present"},
    ], note=NOTES_READ_ONLY))
    return panels


def legacy_parity(columns: Sequence[str],
                  child_tables: Sequence[str]) -> list[dict[str, Any]]:
    """One row per legacy tab: what feeds it in this export, or why nothing can.

    Statuses are three distinct facts and are never merged:

    ``mapped``             the export carries a source for the tab;
    ``no source``          the pipeline does not produce this at all (listed in ``NO_SOURCE``);
    ``missing from export`` the pipeline should carry it but this export does not — a data defect,
                            which names the fields that were looked for.
    """
    present = set(columns)
    tables = set(child_tables)
    rows: list[dict[str, Any]] = []
    for surface, tabs, sources in (("record", RECORD_TABS, RECORD_SOURCES),
                                   ("aggregate", AGGREGATE_TABS, AGGREGATE_SOURCES)):
        for key, label in tabs:
            reason = NO_SOURCE.get((surface, key))
            spec = sources.get(key, {"columns": (), "child": None})
            found = [name for name in spec.get("columns", ()) if name in present]
            child = spec.get("child")
            child_present = bool(child) and child in tables
            if reason:
                status, source = "no source", ""
            elif found or child_present:
                status = "mapped"
                source = ", ".join(found[:4]) + (f" (+{len(found) - 4} more)" if len(found) > 4 else "")
                if child_present:
                    source = (source + " · " if source else "") + f"child table {child}"
            else:
                status = "missing from export"
                source = ", ".join(spec.get("columns", ())[:4]) or (child or "")
            rows.append({"surface": surface, "tab": key, "label": label,
                         "status": status, "source": source,
                         "reason": reason or ""})
    return rows


def render_record_tabs(row: Mapping[str, Any],
                       child_rows: Mapping[str, Sequence[Mapping[str, Any]]] | None = None) -> None:
    """Render the nine legacy tabs for one record. Streamlit is imported lazily (tests import this
    module without a browser runtime)."""
    import streamlit as st

    panels = record_panels(row, child_rows)
    tabs = st.tabs([panel["label"] for panel in panels])
    for tab, panel in zip(tabs, panels):
        with tab:
            if panel["note"]:
                st.caption(panel["note"])
            for block in panel["blocks"]:
                st.markdown(f"**{block['label']}**")
                st.text(block["value"])
            if panel["missing"]:
                st.caption("Not carried by this export for this record: "
                           + ", ".join(panel["missing"])
                           + ". Unavailable is not the same as empty.")


def render_parity_table(columns: Sequence[str], child_tables: Sequence[str]) -> None:
    """Show the parity claim the dashboard is making, tab by tab."""
    import pandas as pd
    import streamlit as st

    rows = legacy_parity(columns, child_tables)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    unmapped = [row for row in rows if row["status"] != "mapped"]
    if unmapped:
        st.caption("Tabs not mapped to this export: "
                   + "; ".join(f"{row['label']} ({row['status']})" for row in unmapped)
                   + ". They are listed here rather than rendered empty.")
