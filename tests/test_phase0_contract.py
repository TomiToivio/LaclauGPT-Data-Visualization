from __future__ import annotations

import json
from pathlib import Path

import pytest

from laclaugpt_visualization.data import frame_from_records
from laclaugpt_visualization.phase0_adapter import adapt_phase0

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "phase0"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_analyzed_contract_prefers_validated_summary_and_preserves_analysis_payloads() -> None:
    record = load_fixture("analyzed.json")

    result = adapt_phase0(record)

    assert result["source_url"] == "https://example.test/phase0/analyzed"
    assert result["document_id"] == "phase0-fixture-analyzed"
    assert result["summary"] == "Validated synthetic summary."
    assert result["entities"] == ["Synthetic Research Lab"]
    assert result["topics"] == ["AI policy"]
    assert result["signifiers"] == ["safety", "control"]
    assert result["formations"] == ["ai critical", "left"]
    assert result["analysis_status"] == "analyzed"
    raw = result["phase0_compatibility"]["raw_phase0"]
    assert raw["phase0_discourse"]["nodal_point_candidates"] == ["AI"]
    assert raw["phase0_ontology"]["nodes"] == [{"id": "AI", "type": "candidate"}]


@pytest.mark.parametrize(
    ("fixture_name", "failed_stage", "expected_error", "raw_key"),
    [
        (
            "summary_validation_error.json",
            "summary",
            "summary failed schema validation",
            "phase0_summary_raw",
        ),
        (
            "discourse_error.json",
            "discourse",
            "discourse output invalid",
            "phase0_discourse_raw",
        ),
    ],
)
def test_error_contract_preserves_stage_error_and_raw_debug_payload(
    fixture_name: str,
    failed_stage: str,
    expected_error: str,
    raw_key: str,
) -> None:
    result = adapt_phase0(load_fixture(fixture_name))

    assert result["analysis_status"] == "error"
    assert result["phase0_stage_status"][failed_stage]["error"] == expected_error
    assert raw_key in result["phase0_compatibility"]["raw_phase0"]


def test_partial_contract_marks_missing_stages_pending_without_inference() -> None:
    result = adapt_phase0(load_fixture("partial.json"))

    assert result["source_url"] == "urn:laclaugpt:synthetic:phase0:partial"
    assert result["source_language"] == "fi"
    assert result["source_arena"] == "grassroots"
    assert result["analysis_status"] == "awaiting-analysis"
    assert result["summary"] == ""
    assert result["entities"] == []
    assert result["topics"] == []
    assert result["signifiers"] == []
    assert result["phase0_stage_status"]["summary"]["status"] == "pending"
    assert result["phase0_stage_status"]["postprocess"]["status"] == "pending"
    assert result["phase0_stage_status"]["discourse"]["status"] == "pending"


def test_contract_fixtures_flow_through_visualization_boundary_offline() -> None:
    records = [
        load_fixture("analyzed.json"),
        load_fixture("summary_validation_error.json"),
        load_fixture("discourse_error.json"),
        load_fixture("partial.json"),
    ]

    frame = frame_from_records(records)

    assert list(frame["source_url"]) == [
        "https://example.test/phase0/analyzed",
        "https://example.test/phase0/summary-error",
        "https://example.test/phase0/discourse-error",
        "urn:laclaugpt:synthetic:phase0:partial",
    ]
    assert list(frame["analysis_status"]) == [
        "analyzed",
        "error",
        "error",
        "awaiting-analysis",
    ]
    assert list(frame["document_id"]) == list(frame["source_url"])
