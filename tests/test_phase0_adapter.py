from __future__ import annotations

from copy import deepcopy

from laclaugpt_visualization.data import frame_from_records
from laclaugpt_visualization.phase0_adapter import adapt_phase0, looks_like_phase0


def _analyzed_record() -> dict:
    return {
        "_id": "mongo-internal-id",
        "document_id": "phase0-doc-1",
        "source_url": "https://example.test/ai",
        "source_date": "2026-09-18T12:00:00Z",
        "actor_name": "Example Lab",
        "arena": "elites",
        "language": "en",
        "title": "AI policy",
        "ai_formation": "ai critical",
        "metadata": {"political_formation": "left"},
        "phase0_summary": {
            "summary": "Unvalidated fallback summary.",
            "entities": ["Example Lab"],
            "topics": ["AI policy"],
            "signifiers": ["safety"],
        },
        "phase0_summary_validated": {
            "document_id": "phase0-doc-1",
            "source_url": "https://example.test/ai",
            "source_date": "2026-09-18T12:00:00Z",
            "actor_name": "Example Lab",
            "title": "AI policy",
            "summary": "Validated summary.",
            "entities": ["Example Lab"],
            "topics": ["AI policy"],
            "signifiers": ["safety"],
        },
        "phase0_discourse": {
            "signifiers": ["control"],
            "nodal_point_candidates": ["AI"],
        },
        "phase0_ontology": {"nodes": [{"id": "AI"}]},
        "phase0": {
            "preprocess": {"status": "ok", "updated_at": "2026-09-18T12:01:00Z"},
            "summary": {"status": "ok", "updated_at": "2026-09-18T12:02:00Z"},
            "postprocess": {"status": "ok", "updated_at": "2026-09-18T12:03:00Z"},
            "discourse": {"status": "ok", "updated_at": "2026-09-18T12:04:00Z"},
        },
    }


def test_adapt_phase0_maps_descriptive_fields_without_mutating_input() -> None:
    record = _analyzed_record()
    original = deepcopy(record)

    result = adapt_phase0(record)

    assert record == original
    assert result["source_url"] == "https://example.test/ai"
    assert result["document_id"] == "phase0-doc-1"
    assert result["source_author"] == "Example Lab"
    assert result["source_arena"] == "elites"
    assert result["source_language"] == "en"
    assert result["content_title"] == "AI policy"
    assert result["summary"] == "Validated summary."
    assert result["entities"] == ["Example Lab"]
    assert result["topics"] == ["AI policy"]
    assert result["signifiers"] == ["safety", "control"]
    assert result["formations"] == ["ai critical", "left"]
    assert result["analysis_status"] == "analyzed"


def test_adapt_phase0_keeps_compatibility_provenance_explicit() -> None:
    result = adapt_phase0(_analyzed_record())

    assert "provenance" not in result
    assert "review" not in result
    assert "review_status" not in result
    compatibility = result["phase0_compatibility"]
    assert compatibility["canonical_phase1_record"] is False
    assert compatibility["source_identity"] == "source_url"
    assert compatibility["label_semantics"]["discourse_signifiers"] == "candidate"
    assert compatibility["label_semantics"]["formations"] == "provisional-context"
    assert compatibility["raw_phase0"]["phase0_ontology"]["nodes"] == [{"id": "AI"}]


def test_adapt_phase0_reports_awaiting_and_missing_optional_fields() -> None:
    record = {
        "source_url": "urn:test:awaiting",
        "phase0": {"preprocess": {"status": "ok"}},
    }

    result = adapt_phase0(record)

    assert result["analysis_status"] == "awaiting-analysis"
    assert result["summary"] == ""
    assert result["entities"] == []
    assert result["topics"] == []
    assert result["signifiers"] == []
    assert result["formations"] == []
    assert result["phase0_stage_status"]["summary"]["status"] == "pending"
    assert result["phase0_stage_status"]["discourse"]["status"] == "pending"


def test_adapt_phase0_reports_stage_error_and_preserves_debug_payload() -> None:
    record = {
        "source_url": "https://example.test/error",
        "phase0_summary_raw": "<bad-json>",
        "phase0_summary_validation_error": "summary failed validation",
        "phase0": {
            "preprocess": {"status": "ok"},
            "summary": {"status": "error", "error": "JSON parse failed"},
        },
    }

    result = adapt_phase0(record)

    assert result["analysis_status"] == "error"
    assert result["phase0_stage_status"]["summary"]["error"] == "JSON parse failed"
    raw = result["phase0_compatibility"]["raw_phase0"]
    assert raw["phase0_summary_raw"] == "<bad-json>"
    assert raw["phase0_summary_validation_error"] == "summary failed validation"


def test_frame_from_records_uses_phase0_adapter_and_source_url_identity() -> None:
    record = _analyzed_record()
    assert looks_like_phase0(record)

    frame = frame_from_records([record])

    assert frame.loc[0, "source_url"] == "https://example.test/ai"
    assert frame.loc[0, "document_id"] == "https://example.test/ai"
    assert frame.loc[0, "analysis_status"] == "analyzed"
    assert frame.loc[0, "signifiers"] == ["safety", "control"]
    assert "_id" not in frame.columns
