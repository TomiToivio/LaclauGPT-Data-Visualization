from __future__ import annotations

import json
from pathlib import Path

import pytest

from laclaugpt_visualization.phase0_browser import (
    browser_enabled,
    inspection_payload,
    phase0_collection_name,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "phase0"


def fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_browser_is_off_by_default_and_opt_in() -> None:
    assert browser_enabled({}) is False
    assert browser_enabled({"LACLAUGPT_VIS_PHASE0_BROWSER_ENABLED": "true"}) is True


def test_collection_name_preserves_phase0_contract() -> None:
    assert phase0_collection_name("ai26") == "laclaugpt2_ai26_scraper_collection"


def test_inspection_analyzed_keeps_source_url_identity_and_candidate_label() -> None:
    payload = inspection_payload(fixture("analyzed.json"))
    assert payload is not None
    assert payload["source_url"] == "https://example.test/phase0/analyzed"
    assert payload["analysis_status"] == "analyzed"
    assert payload["summary"] == "Validated synthetic summary."
    assert payload["candidate_semantics"] == "candidate / provisional"
    assert payload["discourse_candidates"]["nodal_point_candidates"] == ["AI"]


def test_inspection_awaiting_does_not_infer_analysis() -> None:
    payload = inspection_payload(fixture("partial.json"))
    assert payload is not None
    assert payload["analysis_status"] == "awaiting-analysis"
    assert payload["stage_status"]["summary"]["status"] == "pending"
    assert payload["discourse_candidates"] == {}


@pytest.mark.parametrize(
    ("name", "error_key", "raw_key"),
    [
        ("summary_validation_error.json", "summary_validation", "phase0_summary_raw"),
        ("discourse_error.json", "discourse", "phase0_discourse_raw"),
    ],
)
def test_inspection_errors_preserve_validation_and_raw_debug(
    name: str, error_key: str, raw_key: str
) -> None:
    payload = inspection_payload(fixture(name))
    assert payload is not None
    assert payload["analysis_status"] == "error"
    assert error_key in payload["validation_errors"]
    assert raw_key in payload["raw_debug"]


def test_inspection_missing_document_is_explicit() -> None:
    assert inspection_payload(None) is None
