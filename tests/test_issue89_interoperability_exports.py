from __future__ import annotations

import copy
import json

import pytest

from laclaugpt_visualization.canonical_export import (
    CanonicalExportError,
    canonical_interop_record,
    canonical_jsonl,
)


def _canonical_record() -> dict:
    return {
        "_id": "mongo-only-id",
        "schema_version": "2.0",
        "source_url": "https://example.org/post/1",
        "source_native_ids": {"platform": "abc-1"},
        "source_units": [{"id": "unit-1", "kind": "post"}],
        "alignments": [],
        "raw_capture": {
            "ref": "s3://example/raw/1",
            "payload": None,
            "metadata": {"preservation": "reference-only"},
        },
        "source": {
            "platform": "example",
            "author": "researcher",
            "created_at": "2026-09-20T12:00:00Z",
        },
        "content": {"text": "Ääni ja tekoäly", "language": "fi"},
        "intermediate": {"ocr": [], "frames": [], "stage_outputs": {}},
        "analysis": {
            "status": "complete",
            "summary": "Canonical summary",
            "relations": [
                {
                    "id": "rel-1",
                    "source": "actor:1",
                    "target": "concept:1",
                    "evidence_refs": ["ev-1"],
                }
            ],
        },
        "human_readable": {"summary": "Canonical summary", "markdown": ""},
        "review": {"status": "PROVISIONAL"},
        "legacy": {},
        "evidence": [
            {
                "id": "ev-1",
                "source_url": "https://example.org/post/1",
                "quote": "tekoäly",
            }
        ],
        "provenance": [
            {
                "id": "prov-1",
                "kind": "analysis_run",
                "created_at": "2026-09-20T12:01:00Z",
            }
        ],
        "searchable_text": "runtime helper",
        "raw_record": {"private": "view-only alias"},
    }


def test_canonical_export_preserves_identity_evidence_and_provenance_without_mutation() -> None:
    source = _canonical_record()
    before = copy.deepcopy(source)

    exported = canonical_interop_record(source)

    assert exported["source_url"] == source["source_url"]
    assert exported["evidence"] == source["evidence"]
    assert exported["provenance"] == source["provenance"]
    assert exported["review"] == {"status": "PROVISIONAL"}
    assert "_id" not in exported
    assert "searchable_text" not in exported
    assert "raw_record" not in exported
    assert source == before


def test_canonical_jsonl_is_deterministic_unicode_and_traceable() -> None:
    first = _canonical_record()
    second = _canonical_record()
    second["source_url"] = "https://example.org/post/2"
    second["evidence"][0]["source_url"] = second["source_url"]

    payload = canonical_jsonl([first, second])
    rows = [json.loads(line) for line in payload.splitlines()]

    assert payload.endswith("\n")
    assert "Ääni ja tekoäly" in payload
    assert [row["source_url"] for row in rows] == [
        "https://example.org/post/1",
        "https://example.org/post/2",
    ]
    assert rows[0]["evidence"][0]["source_url"] == rows[0]["source_url"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source", []),
        ("analysis", "not-an-object"),
        ("evidence", {}),
        ("provenance", "not-a-list"),
    ],
)
def test_canonical_export_refuses_lossy_schema_coercion(field: str, value: object) -> None:
    record = _canonical_record()
    record[field] = value

    with pytest.raises(CanonicalExportError, match=field):
        canonical_interop_record(record)


def test_canonical_export_rejects_phase0_or_unidentified_records() -> None:
    with pytest.raises(CanonicalExportError, match="source_url"):
        canonical_interop_record({"schema_version": "2.0", "phase0": {"summary": {}}})

    with pytest.raises(CanonicalExportError, match="schema_version"):
        canonical_interop_record({"source_url": "https://example.org/phase0", "phase0": {}})
