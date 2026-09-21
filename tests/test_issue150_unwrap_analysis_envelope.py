"""Issue #150: Visualization must unwrap a stored analysis-result envelope.

Data Analysis persists results as a transport envelope — identity/diagnostics at the top
level with the canonical record nested under ``result`` (``MongoTaskStore.write_result``):

    {
      "project_id": ..., "run_id": ..., "idempotency_key": ...,
      "source_url": ...,
      "result": { <canonical record> },
      "provenance": {...},          # worker provenance (a mapping)
      "created_at": ...,
    }

Visualization's adapters read canonical fields from the top level, so an envelope
flattened to an empty ``analysis`` and every analysed document rendered as
``collection-only``. These tests pin the read-side unwrap.
"""
from __future__ import annotations

from laclaugpt_visualization.canonical import (
    flatten_canonical,
    reconstruct_canonical,
    unwrap_envelope,
)


def _canonical_record() -> dict:
    """A minimal canonical record as it appears nested under ``result``."""
    return {
        "schema_version": "1.1.0",
        "source_url": "https://example.invalid/analysed",
        "source_native_ids": {"document_id": "doc-1"},
        "source": {
            "platform": "web",
            "author": "Example Author",
            "created_at": "2026-09-01T10:00:00Z",
            "collected_at": "2026-09-01T11:00:00Z",
            "raw_ref": "raw://doc-1",
        },
        "content": {"text": "Text about AI governance.", "language": "en", "title": "AI policy"},
        "intermediate": {},
        "raw_capture": {"ref": "raw://doc-1"},
        "analysis": {
            "status": "analyzed",
            "completed_at": "2026-09-01T12:00:00Z",
            "summary": "A summary.",
            "formations": ["ai_safety"],
            "signifiers": ["safety"],
            "entities": [{"label": "European Union"}, {"label": "Google"}],
            "claims": [{"text": "Regulation is needed."}],
        },
        "human_readable": {"summary": "Readable.", "markdown": "## Readable"},
        "evidence": [{"ref": "evidence:1"}],
        "review": {"status": "PROVISIONAL"},
        "provenance": [
            {
                "stage": "analysis",
                "codebook_sha256": "cb-abc",
                "config_sha256": "cfg-abc",
                "model": "gemma4:12b",
                "created_at": "2026-09-01T12:00:00Z",
            }
        ],
        "legacy": {},
    }


def _stored_envelope() -> dict:
    """The envelope exactly as Analysis stores it."""
    return {
        "_id": "mongo-internal",
        "project_id": "ai26",
        "run_id": "ai26-distributed-001",
        "idempotency_key": "analysis:doc-1:v1",
        "source_url": "https://example.invalid/analysed",
        "result": _canonical_record(),
        "provenance": {"worker_id": "laskin-cron", "model": "gemma4:12b"},
        "created_at": 1789976743.98,
    }


# --------------------------------------------------------------------------
# the regression
# --------------------------------------------------------------------------

def test_stored_envelope_renders_as_analyzed() -> None:
    """Before the fix this flattened to 'collection-only' with empty analysis."""
    flat = flatten_canonical(_stored_envelope())

    assert flat["analysis_status"] == "analyzed"
    assert flat["schema_version"] == "1.1.0"


def test_stored_envelope_exposes_analysis_content() -> None:
    """The analysis content the dashboard reads must survive the round trip."""
    flat = flatten_canonical(_stored_envelope())

    assert flat["formations"] == ["ai_safety"]
    assert flat["signifiers"] == ["safety"]
    assert flat["entities"] == ["European Union", "Google"]
    assert flat["summary"] == "A summary."
    assert flat["analysis_timestamp"] == "2026-09-01T12:00:00Z"


def test_stored_envelope_preserves_source_identity_and_text() -> None:
    flat = flatten_canonical(_stored_envelope())

    assert flat["source_url"] == "https://example.invalid/analysed"
    assert flat["document_id"] == "https://example.invalid/analysed"
    assert flat["source_text"] == "Text about AI governance."
    assert flat["source_author"] == "Example Author"


# --------------------------------------------------------------------------
# the provenance trap: nested list must not be replaced by the envelope mapping
# --------------------------------------------------------------------------

def test_canonical_provenance_list_is_not_clobbered_by_envelope_provenance() -> None:
    """The envelope's provenance is a mapping; the canonical one is a list."""
    record = reconstruct_canonical(_stored_envelope())

    provenance = record["provenance"]
    assert isinstance(provenance, list), "the canonical provenance list must win"
    assert provenance[0]["codebook_sha256"] == "cb-abc"
    assert provenance[0]["model"] == "gemma4:12b"


def test_envelope_provenance_is_kept_as_transport_provenance() -> None:
    record = reconstruct_canonical(_stored_envelope())

    assert record["transport_provenance"]["worker_id"] == "laskin-cron"


def test_envelope_identity_fields_are_retained() -> None:
    record = reconstruct_canonical(_stored_envelope())

    assert record["run_id"] == "ai26-distributed-001"
    assert record["idempotency_key"] == "analysis:doc-1:v1"
    assert record["project_id"] == "ai26"


# --------------------------------------------------------------------------
# must not regress the already-flat shape, or unwrap unrelated documents
# --------------------------------------------------------------------------

def test_already_flat_canonical_record_is_unchanged() -> None:
    """A record whose canonical fields are already top-level must not be rewritten."""
    flat_record = _canonical_record()
    before = dict(flat_record)

    assert unwrap_envelope(flat_record) == before
    assert flatten_canonical(flat_record)["analysis_status"] == "analyzed"


def test_document_with_a_non_canonical_result_field_is_untouched() -> None:
    """An unrelated ``result`` payload must not be mistaken for a canonical record."""
    generic = {
        "source_url": "https://example.invalid/other",
        "result": {"exit_code": 0, "stdout": "ok"},   # no canonical markers
        "schema_version": "1.0.0",
    }

    assert unwrap_envelope(generic)["result"] == {"exit_code": 0, "stdout": "ok"}


def test_document_without_result_field_is_untouched() -> None:
    record = {"source_url": "https://example.invalid/plain", "schema_version": "1.1.0"}

    assert unwrap_envelope(record) == record


def test_non_mapping_result_field_is_ignored() -> None:
    """A string/list ``result`` must not be treated as a record."""
    for value in ("text", ["a"], 42, None):
        record = {"source_url": "https://example.invalid/x", "result": value}
        assert unwrap_envelope(record) == record


def test_envelope_without_source_url_still_resolves_identity_from_nested_record() -> None:
    """Identity must survive if the envelope omits source_url."""
    envelope = _stored_envelope()
    del envelope["source_url"]

    flat = flatten_canonical(envelope)

    assert flat["source_url"] == "https://example.invalid/analysed"
    assert flat["analysis_status"] == "analyzed"
