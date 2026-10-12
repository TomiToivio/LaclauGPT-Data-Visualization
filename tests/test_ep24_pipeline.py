"""Synthetic tests for the EP24 reprocessed-pipeline view model (issue #177, step 1).

Fixtures here are invented tiny rows; no real EP24 records are used. The tests pin the
two properties that matter: nothing is invented for a field the pipeline does not emit,
and the human and machine annotation columns never merge.

Run: pytest
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laclaugpt_visualization.ep24_pipeline import (
    BOOTSTRAP_ADDED_COLUMNS,
    EP24_STAGES,
    EP24_VIEW_MODEL_VERSION,
    HUMAN_ANNOTATION_COLUMNS,
    MACHINE_ANNOTATION_COLUMNS,
    SOURCE_COLUMNS,
    STAGES_BY_NUMBER,
    STEP_ZERO_COLUMNS,
    StageStatus,
    classify_status_value,
    combined_columns,
    missing_columns,
    normalize_document,
    pipeline_overview,
    stage_report,
)


def a_full_row() -> dict[str, str]:
    """One synthetic row that has completed every stage the dataframe can report."""
    return {
        "country": "Finland",
        "author_username": "example_user",
        "account_type": "creator",
        "source_type": "tiktok",
        "source_recording": "example_recording",
        "video_id": "vid-0001",
        "sequence_number": "1",
        "political_preference": "",
        "allas_filename": "example_0001.mp4",
        "entities": "Example Party",
        "themes": "housing",
        "video_duration": "30",
        "researcher_note": "checked by hand",
        "_storage_id": "store-0001",
        "preprocess_status": "ok",
        "asr_transcript": "example transcript",
        "ocr_1": "example overlay text",
        "preprocess_completed_at": "2026-01-01T00:00:00Z",
        "frame_analysis_status": "ok",
        "frame_analysis_1": "a described frame",
        "vllm_video_status": "ok",
        "vllm_video_analysis": "a described video",
        "SCROLL": "no",
        "summary_quality_status": "ok",
        "summary_analysis": "a fused summary",
        "processing_status": "ok",
        "postprocess_entities": '["Example Party"]',
        "postprocess_themes": '["housing"]',
        "laclau_status": "ok",
        "laclau_structured_json": '{"us": ["housing"]}',
        "dna_status": "ok",
        "dna_statements_json": '[{"actor": "Example Party"}]',
        "sna_analysis_markdown": "no evidenced ties",
        "sna_edges_json": "[]",
    }


# --------------------------------------------------------------------------- #
# The contract itself
# --------------------------------------------------------------------------- #

def test_nine_numbered_stages_in_order() -> None:
    assert [s.number for s in EP24_STAGES] == list(range(1, 10))


def test_stage_keys_match_the_issue_wording() -> None:
    assert STAGES_BY_NUMBER[6].key == "discourse_analysis"
    assert STAGES_BY_NUMBER[7].key == "discourse_network_analysis"
    assert STAGES_BY_NUMBER[8].key == "social_network_analysis"
    assert STAGES_BY_NUMBER[9].key == "rdf"


def test_real_field_names_are_recorded_per_stage() -> None:
    """Spot-check names actually read from the analysis stage contract."""
    assert "asr_transcript" in STAGES_BY_NUMBER[1].evidence_columns
    assert "frame_analysis_1" in STAGES_BY_NUMBER[2].evidence_columns
    assert "SCROLL" in STAGES_BY_NUMBER[3].evidence_columns
    assert "summary_summary_md" in STAGES_BY_NUMBER[4].evidence_columns
    assert "ep24_codebook_fingerprint" in STAGES_BY_NUMBER[5].output_columns
    assert "laclau_abstention_reason" in STAGES_BY_NUMBER[6].evidence_columns
    assert "dna_statements_json" in STAGES_BY_NUMBER[7].evidence_columns
    assert "sna_edges_json" in STAGES_BY_NUMBER[8].evidence_columns


def test_source_and_bootstrap_identity_columns() -> None:
    assert "video_id" in SOURCE_COLUMNS
    assert "_storage_id" in BOOTSTRAP_ADDED_COLUMNS


def test_step_nine_writes_no_dataframe_columns() -> None:
    assert STAGES_BY_NUMBER[9].writes_dataframe_columns is False


def test_step_eight_has_no_status_column() -> None:
    """The pipeline emits no Step 8 status. The model must not pretend otherwise."""
    assert STAGES_BY_NUMBER[8].status_column is None


# --------------------------------------------------------------------------- #
# Status classification
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw,expected", [
    ("ok", StageStatus.COMPLETE),
    ("OK", StageStatus.COMPLETE),
    ("completed", StageStatus.COMPLETE),
    ("failed", StageStatus.FAILED),
    ("error", StageStatus.FAILED),
    ("", StageStatus.MISSING),
    (None, StageStatus.MISSING),
    ("nan", StageStatus.MISSING),
    ("something-new", StageStatus.REPORTED_OTHER),
])
def test_classify_status_value(raw, expected) -> None:
    assert classify_status_value(raw) is expected


def test_an_unrecognised_status_is_preserved_verbatim() -> None:
    """Not guessing must not mean losing the value."""
    report = stage_report({"preprocess_status": "needs_resplit"}, STAGES_BY_NUMBER[1])
    assert report.status is StageStatus.REPORTED_OTHER
    assert report.raw == "needs_resplit"


# --------------------------------------------------------------------------- #
# Per-stage reporting, including the honest absences
# --------------------------------------------------------------------------- #

def test_a_full_row_completes_every_reportable_stage() -> None:
    view = normalize_document(a_full_row())
    completed = set(view.completed_steps())
    assert completed == {1, 2, 3, 4, 5, 6, 7, 8}


def test_step_nine_reports_not_exported_rather_than_complete() -> None:
    view = normalize_document(a_full_row())
    assert view.stage(9).status is StageStatus.NOT_EXPORTED


def test_step_eight_status_is_derived_and_labelled() -> None:
    view = normalize_document(a_full_row())
    report = view.stage(8)
    assert report.status is StageStatus.COMPLETE
    assert report.derived is True, "an inferred Step 8 status must be marked as derived"


def test_step_eight_without_artifacts_is_missing() -> None:
    row = a_full_row()
    row["sna_analysis_markdown"] = ""
    row["sna_edges_json"] = ""
    assert stage_report(row, STAGES_BY_NUMBER[8]).status is StageStatus.MISSING


def test_a_failed_stage_is_visible_and_keeps_its_message() -> None:
    row = a_full_row()
    row["dna_status"] = "failed"
    row["dna_error"] = "timeout"
    report = stage_report(row, STAGES_BY_NUMBER[7])
    assert report.status is StageStatus.FAILED
    assert report.raw == "failed"


def test_an_empty_row_invents_nothing() -> None:
    view = normalize_document({})
    for report in view.stages:
        if report.number == 9:
            assert report.status is StageStatus.NOT_EXPORTED
        elif report.number == 8:
            assert report.status is StageStatus.MISSING
        else:
            assert report.status is StageStatus.MISSING
    assert view.completed_steps() == ()


def test_missing_optional_multimodal_fields_stay_absent() -> None:
    """A text-only record must not gain transcript/OCR/frame values."""
    row = {"_storage_id": "s", "video_id": "v", "country": "Poland"}
    view = normalize_document(row)
    assert view.stage(1).status is StageStatus.MISSING
    assert view.stage(1).has_output is False


# --------------------------------------------------------------------------- #
# Identity and the annotation boundary
# --------------------------------------------------------------------------- #

def test_identity_uses_storage_id_and_video_id() -> None:
    view = normalize_document(a_full_row())
    assert view.storage_id == "store-0001"
    assert view.video_id == "vid-0001"
    assert view.country == "Finland"


def test_other_identifiers_stay_aliases() -> None:
    view = normalize_document(a_full_row())
    assert "example_0001.mp4" in view.identity_aliases
    assert view.identity_aliases != (view.storage_id,)


def test_human_and_machine_annotations_never_merge() -> None:
    view = normalize_document(a_full_row())
    assert view.human_annotations["entities"] == "Example Party"
    assert view.machine_annotations["postprocess_entities"] == '["Example Party"]'
    assert not set(view.human_annotations) & set(view.machine_annotations)


def test_the_annotation_column_sets_are_disjoint_by_construction() -> None:
    assert not set(HUMAN_ANNOTATION_COLUMNS) & set(MACHINE_ANNOTATION_COLUMNS)


# --------------------------------------------------------------------------- #
# Overview, preflight and serialization
# --------------------------------------------------------------------------- #

def test_overview_counts_every_stage_state() -> None:
    rows = [a_full_row(), {}, {"preprocess_status": "failed", "dna_status": "some-new-value"}]
    overview = pipeline_overview(rows)
    assert overview.documents == 3
    assert overview.by_stage[1]["complete"] == 1
    assert overview.by_stage[1]["missing"] == 1
    assert overview.by_stage[1]["failed"] == 1
    assert overview.by_stage[9]["not_exported"] == 3
    assert overview.by_stage[8]["missing"] == 2


def test_overview_never_reports_a_stage_as_complete_when_it_has_no_status() -> None:
    overview = pipeline_overview([{"preprocess_status": "ok"}])
    assert "complete" not in overview.by_stage[9]


def test_combined_columns_covers_source_and_every_stage_field() -> None:
    columns = combined_columns()
    for column in SOURCE_COLUMNS + BOOTSTRAP_ADDED_COLUMNS:
        assert column in columns
    assert "asr_transcript" in columns
    assert "dna_statements_json" in columns
    assert len(columns) == len(set(columns)), "columns must not be duplicated"


def test_missing_columns_reports_absences_rather_than_faking_them() -> None:
    absent = missing_columns({"video_id", "_storage_id"})
    assert "asr_transcript" in absent
    assert "video_id" not in absent


def test_view_model_serializes_deterministically() -> None:
    first = normalize_document(a_full_row()).to_dict()
    second = normalize_document(a_full_row()).to_dict()
    assert first == second
    assert first["view_model_version"] == EP24_VIEW_MODEL_VERSION


def test_the_module_imports_no_network_client_at_import_time() -> None:
    """AGENTS.md rule 8: never connect to a network service at import time."""
    import sys

    for blocked in ("pymongo", "redis", "boto3", "requests"):
        assert blocked not in sys.modules, f"{blocked} was imported as a side effect"


# --------------------------------------------------------------------------- #
# The field names must be real
# --------------------------------------------------------------------------- #

_CONTRACT = json.loads(
    (Path(__file__).parent / "fixtures" / "ep24_contract_columns_v1.json").read_text(encoding="utf-8")
)


def _declared_columns() -> set[str]:
    declared = set(SOURCE_COLUMNS) | set(BOOTSTRAP_ADDED_COLUMNS) | set(STEP_ZERO_COLUMNS)
    declared |= set(HUMAN_ANNOTATION_COLUMNS) | set(MACHINE_ANNOTATION_COLUMNS)
    for stage in EP24_STAGES:
        declared |= set(stage.evidence_columns) | set(stage.output_columns)
        if stage.status_column:
            declared.add(stage.status_column)
    return declared


def test_every_declared_column_exists_in_the_recorded_pipeline_contract() -> None:
    """A field name invented on the visualization side must fail here, not in a dashboard.

    The snapshot in ``fixtures/ep24_contract_columns_v1.json`` was read from the sibling
    repository's ``ep24_stage_contract.py``. This repository does not import that module
    (AGENTS.md rule 2), so the names are pinned by recorded data instead.
    """
    real = set(_CONTRACT["columns"])
    invented = sorted(_declared_columns() - real)
    assert invented == [], f"declared but not emitted by the EP24 pipeline: {invented}"


def test_the_contract_snapshot_records_its_provenance() -> None:
    provenance = _CONTRACT["provenance"]
    assert provenance["source_module"] == "ep24_stage_contract.py"
    assert provenance["source_commit"]
    assert len(_CONTRACT["columns"]) == _CONTRACT["column_count"]


def test_step_five_machine_columns_are_the_recorded_ones() -> None:
    """Regression pin: two names here were once invented rather than read."""
    outputs = STAGES_BY_NUMBER[5].output_columns
    assert "ep24_memory_sentiment_target_ids_json" in outputs
    assert "ep24_memory_context_json" not in outputs
    assert "ep24_sentiment_target_ids_json" not in outputs


def test_every_status_column_is_a_recorded_pipeline_column() -> None:
    real = set(_CONTRACT["columns"])
    for stage in EP24_STAGES:
        if stage.status_column:
            assert stage.status_column in real, stage.status_column

