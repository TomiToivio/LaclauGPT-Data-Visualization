from __future__ import annotations

import json
import sqlite3

import pandas as pd

from laclaugpt_visualization.data import frame_from_records, load_frame, normalize_frame
from laclaugpt_visualization.legacy_ep24 import adapt as adapt_ep24


def _canonical_record() -> dict:
    return {
        "schema_version": "1.0.0",
        "source_url": "synthetic://canonical/1",
        "source_native_ids": {"video_id": "legacy-video-1"},
        "source": {
            "platform": "synthetic",
            "source_type": "post",
            "author": "fixture",
            "author_fullname": "Synthetic Research Fixture",
            "created_at": "2026-09-15T10:00:00+03:00",
            "collected_at": "2026-09-15T07:05:00Z",
            "collector": "synthetic-test",
            "collection_method": "fixture",
            "language": "en",
            "raw_ref": "synthetic://raw/1",
        },
        "content": {
            "text": "Synthetic source text",
            "transcripts": [{"id": "t1", "text": "Synthetic transcript", "language": "en"}],
            "ocr": [{"id": "o1", "text": "Synthetic OCR"}],
            "frames": [{"id": "frame-1", "timestamp_seconds": 1.0}],
            "media_references": [{"object_ref": "synthetic://media/1"}],
        },
        "evidence": [
            {
                "evidence_id": "evidence-1",
                "kind": "text",
                "source_url": "synthetic://canonical/1",
                "quote": "Synthetic source text",
            }
        ],
        "analysis": {
            "status": "complete",
            "completed_at": "2026-09-15T08:00:00Z",
            "summary": "Synthetic summary",
            "entities": [{"entity_id": "actor-1", "label": "Synthetic Actor"}],
            "entity_mentions": [{"entity_id": "actor-1", "text": "Synthetic Actor"}],
            "topics": [{"label": "AI"}],
            "classifications": [{"label": "synthetic-class"}],
            "formations": [{"object_id": "formation-1", "label": "Synthetic Formation", "kind": "formation"}],
            "signifiers": [{"object_id": "signifier-1", "label": "AI", "kind": "signifier"}],
            "nodal_points": [{"object_id": "nodal-1", "label": "progress", "kind": "nodal_point"}],
            "discourses": [{"object_id": "discourse-1", "label": "Synthetic Discourse", "kind": "discourse"}],
            "imaginaries": [{"object_id": "imaginary-1", "label": "Synthetic Imaginary", "kind": "imaginary"}],
            "us": [{"object_id": "us-1", "label": "researchers", "kind": "us"}],
            "them": [{"object_id": "them-1", "label": "opponents", "kind": "them"}],
            "frontier": [{"object_id": "frontier-1", "label": "researchers/opponents", "kind": "frontier"}],
            "affects": [{"object_id": "affect-1", "label": "hope", "kind": "affect"}],
            "sentiments": [{"object_id": "sentiment-1", "label": "positive", "kind": "sentiment"}],
            "relations": [{"relation_id": "r1", "relation_type": "equivalence", "source_ref": "AI", "target_ref": "progress"}],
            "uncertainty": ["synthetic uncertainty"],
            "abstentions": ["no hegemonic claim"],
            "model_runs": [{"provider": "fake", "model": "fixture"}],
        },
        "provenance": [{"stage": "analysis", "method": "synthetic-test", "created_at": "2026-09-15T08:00:00Z"}],
        "review": {"status": "PROVISIONAL", "note": None},
    }


def _assert_semantics(frame: pd.DataFrame) -> None:
    row = frame.iloc[0]
    assert row["source_url"] == "synthetic://canonical/1"
    assert row["document_id"] == row["source_url"]
    assert row["schema_version"] == "1.0.0"
    assert row["source_type"] == "post"
    assert row["collector"] == "synthetic-test"
    assert row["source_text"] == "Synthetic source text"
    assert row["transcript"] == "Synthetic transcript"
    assert row["ocr"] == ["Synthetic OCR"]
    assert row["entities"] == ["Synthetic Actor"]
    assert row["us"] == ["researchers"]
    assert row["them"] == ["opponents"]
    assert row["review_status"] == "PROVISIONAL"
    assert row["evidence"][0]["evidence_id"] == "evidence-1"
    assert row["provenance"][0]["method"] == "synthetic-test"
    assert str(row["source_timestamp"]) == "2026-09-15 07:00:00+00:00"


def test_jsonl_preserves_canonical_semantics(tmp_path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text(json.dumps(_canonical_record()) + "\n", encoding="utf-8")
    _assert_semantics(load_frame(path))


def test_csv_json_encoded_sections_reconstruct_canonical_record(tmp_path) -> None:
    record = _canonical_record()
    flat = {
        key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
        for key, value in record.items()
    }
    path = tmp_path / "records.csv"
    pd.DataFrame([flat]).to_csv(path, index=False)
    _assert_semantics(load_frame(path))


def test_sqlite_json_encoded_sections_reconstruct_canonical_record(tmp_path) -> None:
    record = _canonical_record()
    flat = {
        key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
        for key, value in record.items()
    }
    path = tmp_path / "records.sqlite3"
    with sqlite3.connect(path) as con:
        pd.DataFrame([flat]).to_sql("annotations", con, index=False)
    _assert_semantics(load_frame(path))


def test_mongo_like_document_ignores_backend_id() -> None:
    record = _canonical_record()
    record["_id"] = "mongodb-implementation-key"
    frame = frame_from_records([record])
    _assert_semantics(frame)
    assert "mongodb-implementation-key" not in frame.iloc[0]["searchable_text"]


def test_dataframe_with_nested_sections_is_view_of_canonical_record() -> None:
    _assert_semantics(normalize_frame(pd.DataFrame([_canonical_record()])))


def test_text_only_record_does_not_invent_multimodal_values() -> None:
    record = _canonical_record()
    record["content"] = {"text": "Only text"}
    frame = frame_from_records([record])
    row = frame.iloc[0]
    assert row["transcript"] == "Only text"
    assert row["ocr"] == []
    assert row["frames"] == []
    assert row["media_references"] == []


def test_legacy_ep24_uses_source_url_as_identity_and_retains_aliases() -> None:
    row = adapt_ep24(
        {
            "new_id": "42",
            "video_id": "video-42",
            "source_url": "https://example.invalid/video/42",
            "whisper_transcript": "Synthetic transcript",
            "ocr_1": "Synthetic OCR",
            "frame_1": "synthetic-frame-ref",
        }
    )
    assert row["source_url"] == "https://example.invalid/video/42"
    assert row["document_id"] == row["source_url"]
    assert row["source_native_ids"]["video_id"] == "video-42"
    assert row["ocr"] == ["Synthetic OCR"]
    assert row["frames"] == ["synthetic-frame-ref"]
