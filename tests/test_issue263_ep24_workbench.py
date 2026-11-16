"""Issue #263: the legacy :8501 workbench's reading half on the reprocessed export.

The parity claim has to be mechanical. For every legacy tab, either a mapped new-data view exists or
the tab is in the documented "no source" list; a tab that is neither is a data defect, and an
unavailable field is reported by name instead of being rendered as an empty finding.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laclaugpt_visualization.ep24_workbench import (
    AGGREGATE_TABS,
    NO_SOURCE,
    NOTES_READ_ONLY,
    RECORD_SOURCES,
    RECORD_TABS,
    children_for,
    legacy_parity,
    record_panels,
)

#: The columns the 2026-11-15 FI/PL/PT export actually carries, restricted to the ones this module
#: reads. The delivered export has 103; naming the whole schema here would make the test a copy of it.
DELIVERED_COLUMNS = [
    "source_key", "country", "source_type", "account_type", "political_preference",
    "author_username", "source_url", "created_at", "source_recording", "video_duration_seconds",
    "video_id", "dataset", "processing_status", "asr_transcript", "asr_translation", "asr_language",
    "ocr_1", "frame_analysis_1", "vllm_video_analysis", "vllm_video_markdown_analysis",
    "summary_analysis", "summary_summary_md", "postprocess_summary_md", "formula_of_populism_analysis",
    "formula_of_populism_us", "formula_of_populism_frontier", "laclau_summary_md", "researcher_note",
    "positive", "neutral", "negative", "language",
]
DELIVERED_CHILDREN = ["entities", "themes", "dna", "sna_nodes", "sna_edges"]


def _row(**fields):
    base = {"country": "finland", "source_key": "ep24:finland:x", "video_id": "v1",
            "source_type": "instagram", "account_type": "party"}
    base.update(fields)
    return base


def test_the_nine_legacy_record_tabs_are_specified_and_sourced():
    labels = [label for _, label in RECORD_TABS]
    assert labels == ["Metadata", "Whisper", "OCR", "Multimodal", "Summary", "Populism", "Themes",
                      "Persons", "Report Problems / Researcher Notes"]
    assert {key for key, _ in RECORD_TABS} == set(RECORD_SOURCES)


def test_parity_maps_every_legacy_tab_on_the_delivered_export_except_the_two_without_a_source():
    rows = legacy_parity(DELIVERED_COLUMNS, DELIVERED_CHILDREN)
    assert len(rows) == len(RECORD_TABS) + len(AGGREGATE_TABS)
    unmapped = {(row["surface"], row["tab"]): row for row in rows if row["status"] != "mapped"}
    assert set(unmapped) == {("aggregate", "topics"), ("aggregate", "manifestoberta")}
    for key, row in unmapped.items():
        assert row["status"] == "no source"
        assert row["reason"] == NO_SOURCE[key]


def test_a_tab_with_neither_column_nor_child_table_is_a_data_defect_not_a_zero():
    columns = [name for name in DELIVERED_COLUMNS if name != "ocr_1"]
    rows = {(row["surface"], row["tab"]): row for row in legacy_parity(columns, DELIVERED_CHILDREN)}
    ocr = rows[("record", "ocr")]
    assert ocr["status"] == "missing from export"
    assert "ocr_1" in ocr["source"]


def test_themes_and_persons_are_mapped_by_the_child_tables_on_the_child_dialect():
    # The delivered export carries no postprocess_themes/postprocess_entities row columns.
    rows = {(row["surface"], row["tab"]): row for row in
            legacy_parity(DELIVERED_COLUMNS, DELIVERED_CHILDREN)}
    assert rows[("record", "themes")]["status"] == "mapped"
    assert "child table themes" in rows[("record", "themes")]["source"]
    assert "child table entities" in rows[("record", "persons")]["source"]


def test_an_unavailable_tab_names_the_fields_it_looked_for():
    panels = {panel["key"]: panel for panel in record_panels(_row())}
    assert panels["ocr"]["blocks"] == []
    assert "ocr_1" in panels["ocr"]["missing"]
    assert panels["whisper"]["missing"]  # no transcript in this record
    assert panels["themes"]["missing"] and "themes.csv" in panels["themes"]["missing"]


def test_platform_is_shown_as_a_derivation_unless_the_export_carries_it():
    derived = {panel["key"]: panel for panel in record_panels(_row())}["metadata"]
    labels = [block["label"] for block in derived["blocks"]]
    assert "Platform note" in labels and "Platform" not in labels
    assert "platform" not in derived["missing"]

    carried = {panel["key"]: panel for panel in
               record_panels(_row(platform="instagram", source_type="instagram"))}["metadata"]
    values = {block["label"]: block["value"] for block in carried["blocks"]}
    assert values["Platform"] == "instagram"
    assert "Platform note" not in values


def test_the_notes_tab_states_that_review_state_is_not_written():
    panels = {panel["key"]: panel for panel in record_panels(_row(researcher_note="check frame 3"))}
    notes = panels["notes"]
    assert notes["note"] == NOTES_READ_ONLY
    assert "does not write" in notes["note"]
    assert [block["label"] for block in notes["blocks"]] == ["Researcher annotation", "Review state"]


@pytest.mark.parametrize("fields", [
    {"whisper_transcript": "legacy transcript", "whisper_translation": "legacy translation"},
    {"asr_transcript": "reprocessed transcript", "asr_translation": "reprocessed translation"},
])
def test_both_transcript_dialects_fill_the_whisper_tab(fields):
    whisper = {panel["key"]: panel for panel in record_panels(_row(**fields))}["whisper"]
    values = {block["label"]: block["value"] for block in whisper["blocks"]}
    assert values["Transcript (original)"].endswith("transcript")
    assert values["Translation"].endswith("translation")
    assert whisper["missing"] == []


def test_themes_and_persons_read_the_child_rows_for_one_record():
    children = {
        "themes": [{"source_key": "ep24:finland:x", "label": "EP elections 2024"},
                   {"source_key": "ep24:finland:x", "label": "Climate policy"},
                   {"source_key": "ep24:finland:other", "label": "Somebody else"}],
        "entities": [{"source_key": "ep24:finland:x", "label": "Party A"}],
    }
    selected = children_for(children, _row())
    panels = {panel["key"]: panel for panel in record_panels(_row(), selected)}
    themes = panels["themes"]["blocks"][0]["value"]
    assert "EP elections 2024" in themes and "Climate policy" in themes
    assert "Somebody else" not in themes
    assert "Party A" in panels["persons"]["blocks"][0]["value"]
    assert panels["themes"]["missing"] == []


def test_children_are_matched_on_either_identifier_dialect():
    children = {"themes": [{"parent_record_id": "record-9", "label": "Matched by record id"}]}
    assert children_for(children, {"record_id": "record-9"})["themes"][0]["label"] == (
        "Matched by record id")
    assert children_for(children, {"source_key": "other"})["themes"] == []


def test_a_structured_cell_is_rendered_as_allowlisted_text_not_a_raw_dump():
    row = _row(formula_of_populism_analysis=json.dumps(
        {"interpretation": "people vs elite", "prompt": "SECRET-PROMPT"}))
    populism = {panel["key"]: panel for panel in record_panels(row)}["populism"]
    rendered = " ".join(block["value"] for block in populism["blocks"])
    assert "people vs elite" in rendered
    assert "SECRET-PROMPT" not in rendered


def _write_export(root: Path) -> Path:
    """A two-record synthetic export in the delivered shape: one full record, one without evidence."""
    (root / "children").mkdir(parents=True)
    columns = ["source_key", "country", "source_type", "account_type", "political_preference",
               "author_username", "source_url", "created_at", "video_id", "dataset",
               "asr_transcript", "asr_translation", "ocr_1", "frame_analysis_1",
               "summary_summary_md", "formula_of_populism_analysis", "researcher_note",
               "video_duration_seconds"]
    header = ",".join(columns)
    full = {
        "source_key": "ep24:finland:synthetic-1", "country": "finland", "source_type": "instagram",
        "account_type": "party", "political_preference": "right", "author_username": "account-a",
        "source_url": "https://example.invalid/a", "created_at": "2024-05-21T10:00:00+00:00",
        "video_id": "v1", "dataset": "ep2024_reprocess", "asr_transcript": "Spoken words",
        "asr_translation": "Translated words", "ocr_1": "Poster text",
        "frame_analysis_1": "A person speaks", "summary_summary_md": "Summary text",
        "formula_of_populism_analysis": "People against the elite",
        "researcher_note": "checked", "video_duration_seconds": "42",
    }
    empty = {"source_key": "ep24:poland:synthetic-2", "country": "poland",
             "source_type": "facebook", "account_type": "candidate", "video_id": "v2",
             "dataset": "ep2024_reprocess"}
    lines = [header]
    for record in (full, empty):
        lines.append(",".join('"' + str(record.get(name, "")).replace('"', '""') + '"'
                              for name in columns))
    (root / "combined.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "children" / "themes.csv").write_text(
        "child_id,source_key,country,field,index,origin,item.label\n"
        "c1,ep24:finland:synthetic-1,finland,postprocess_themes,0,model_output,EP elections 2024\n",
        encoding="utf-8")
    (root / "children" / "entities.csv").write_text(
        "child_id,source_key,country,field,index,origin,item.label\n"
        "c2,ep24:finland:synthetic-1,finland,postprocess_entities,0,model_output,Party A\n",
        encoding="utf-8")
    return root


def test_the_workbench_view_renders_without_exception(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    root = _write_export(tmp_path / "export")
    monkeypatch.setenv("LACLAUGPT_VIS_ANALYSIS_DATA_DIR", str(root))
    monkeypatch.delenv("LACLAUGPT_VIS_DEMO_PASSWORD", raising=False)

    app = AppTest.from_file(str(ROOT / "src/laclaugpt_visualization/ep24_reprocessed_app.py"))
    app.run(timeout=60)
    assert not app.exception

    next(radio for radio in app.sidebar.radio if radio.label == "Research view").set_value(
        "Video workbench · legacy parity").run(timeout=60)
    assert not app.exception, app.exception
    # Nine legacy per-record tabs are rendered from the workbench, over the real view selection.
    labels = [tab.label for tab in app.tabs]
    for expected in ("Metadata", "Whisper", "OCR", "Multimodal", "Summary", "Populism",
                     "Themes", "Persons", "Report Problems / Researcher Notes"):
        assert expected in labels, (expected, labels)
    body = " ".join([str(element.value) for element in app.markdown]
                    + [str(element.value) for element in app.text])
    assert "EP elections 2024" in body  # the child table reached the Themes tab
    assert "SECRET" not in body
    # The export has no `title`: the picker must fall back to identifiers, not label every row alike.
    picker = next(select for select in app.selectbox if select.label == "Inspect source record")
    assert "Untitled video" not in picker.options[0]
    assert "v1" in picker.options[0]
