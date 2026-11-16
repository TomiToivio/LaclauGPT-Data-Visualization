"""The researcher export allowlist (issue #242).

The tests here are about a boundary, not a feature: a field that is machine plumbing must not reach a
researcher's CSV, and a field nobody classified must stop the export instead of slipping through.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from laclaugpt_visualization.researcher_export import (
    DROPPED,
    RESEARCH_COLUMNS,
    UnclassifiedColumnError,
    classify,
    csv_bytes,
    manifest_fingerprint,
    provenance,
    provenance_json,
    researcher_frame,
    selection_summary,
    served_commit,
)

#: A frame shaped like the served index: researcher fields, machine fields, and nothing invented.
INDEX_COLUMNS = (
    "record_id",
    "country",
    "video_id",
    "author_username",
    "political_preference",
    "asr_model",
    "asr_runtime_ms",
    "_storage_id",
    "allas_filename",
    "vllm_gpu_name",
    "laclau_persistence_status",
    "laclau_prompt_version",
    "_monday500_reused_through",
    "dna_statement_count",
    "sna_status",
    "researcher_note",
    "step_01_status",
)


def index_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "record_id": ["fi/1", "fi/2", "pl/1"],
            "country": ["finland", "finland", "poland"],
            "video_id": ["1", "2", "1"],
            "author_username": ["a", "b", "c"],
            "political_preference": ["government", "opposition", "government"],
            "asr_model": ["whisper-large-v3", "whisper-large-v3", "whisper-large-v3"],
            "asr_runtime_ms": ["900", "1000", "1100"],
            "_storage_id": ["s1", "s2", "s3"],
            "allas_filename": ["x.mp4", "y.mp4", "z.mp4"],
            "vllm_gpu_name": ["H100", "H100", "A100"],
            "laclau_persistence_status": ["stored", "stored", "stored"],
            "laclau_prompt_version": ["v3", "v3", "v3"],
            "_monday500_reused_through": ["step_05", "step_05", "step_05"],
            "dna_statement_count": ["3", "0", "2"],
            "sna_status": ["complete", "not run", "complete"],
            "researcher_note": ["", "check", ""],
            "step_01_status": ["complete", "complete", "complete"],
        }
    )


MANIFEST = {
    "contract": "ep24-reprocessed-view/0.1",
    "builder_version": "live-steps-artifacts-1",
    "dataset": "ep24_monday500_20261031",
    "generated_at": "2026-11-10T10:25:13+00:00",
    "records": 1500,
    "record_counts": {
        "exported_total": 1500,
        "finland": {"exported": 500},
        "poland": {"exported": 500},
        "portugal": {"exported": 500},
    },
}


def test_the_allowlist_and_the_drop_list_never_overlap():
    dropped = {column for columns in DROPPED.values() for column in columns}
    assert not set(RESEARCH_COLUMNS) & dropped


def test_every_researcher_column_is_unique():
    assert len(RESEARCH_COLUMNS) == len(set(RESEARCH_COLUMNS))


def test_classify_keeps_the_findings_and_drops_the_plumbing():
    keep, dropped = classify(INDEX_COLUMNS)
    assert "dna_statement_count" in keep
    assert "researcher_note" in keep
    assert "asr_runtime_ms" not in keep
    dropped_names = {entry["column"] for entry in dropped}
    assert {"asr_runtime_ms", "_storage_id", "vllm_gpu_name"} <= dropped_names
    # every drop is explained, not merely absent
    assert all(entry["reason"] for entry in dropped)


def test_an_unclassified_column_is_excluded_by_default():
    """Default-deny: an unknown producer field must never reach the CSV, and must not crash the UI."""
    keep, dropped = classify([*INDEX_COLUMNS, "brand_new_producer_field"])
    assert "brand_new_producer_field" not in keep
    entry = next(item for item in dropped if item["column"] == "brand_new_producer_field")
    assert "excluded by default" in entry["reason"]


def test_strict_classification_reports_the_drift_instead_of_hiding_it():
    with pytest.raises(UnclassifiedColumnError) as error:
        classify([*INDEX_COLUMNS, "brand_new_producer_field"], strict=True)
    assert "brand_new_producer_field" in str(error.value)


def test_the_projection_keeps_row_order_and_drops_machine_columns():
    frame = index_frame()
    projection = researcher_frame(frame)
    assert list(projection["record_id"]) == ["fi/1", "fi/2", "pl/1"]
    assert "allas_filename" not in projection.columns
    assert set(projection.columns) <= set(RESEARCH_COLUMNS)


def test_the_column_chooser_cannot_widen_the_allowlist():
    projection = researcher_frame(index_frame(), ["country", "allas_filename", "video_id"])
    assert list(projection.columns) == ["country", "video_id"]


def test_an_empty_choice_yields_an_empty_projection_not_the_whole_frame():
    projection = researcher_frame(index_frame(), [])
    assert projection.empty
    assert len(projection) == 0


def test_the_csv_is_utf8_with_a_bom_for_spreadsheets():
    payload = csv_bytes(researcher_frame(index_frame()))
    assert payload.startswith(b"\xef\xbb\xbf")
    text = payload.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("record_id,country")
    assert text.count("\n") == 4  # header + three rows, lineterminator only


def test_the_selection_summary_counts_rows_and_countries():
    summary = selection_summary(index_frame())
    assert summary["rows"] == 3
    assert summary["countries"] == {"finland": 2, "poland": 1}


def test_provenance_names_the_build_the_code_and_every_dropped_column():
    payload = provenance(
        MANIFEST,
        frame=index_frame(),
        selection=index_frame().iloc[:2],
        commit="abc1234",
        exported_at=datetime(2026, 11, 15, 12, 0, tzinfo=UTC),
    )
    assert payload["dataset"] == "ep24_monday500_20261031"
    assert payload["served_commit"] == "abc1234"
    assert payload["selection"]["rows"] == 2
    assert payload["dropped_columns"]
    assert all(entry["reason"] for entry in payload["dropped_columns"])
    assert payload["manifest_sha256"] == manifest_fingerprint(MANIFEST)
    assert payload["exported_at"] == "2026-11-15T12:00:00+00:00"


def test_provenance_json_is_stable_and_readable():
    payload = provenance(MANIFEST, frame=index_frame(), selection=index_frame(), commit=None)
    first = provenance_json(payload)
    second = provenance_json(payload)
    assert first == second
    assert json.loads(first)["contract"] == "ep24-researcher-export/1"


def test_an_unknown_commit_is_reported_as_unknown_not_invented(tmp_path):
    assert served_commit(tmp_path) is None
    assert served_commit(None) is None
