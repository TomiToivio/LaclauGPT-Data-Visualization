import json

from laclaugpt_visualization.data import filter_frame, load_frame
from laclaugpt_visualization.review import Review, SQLiteReviewStore
from laclaugpt_visualization.transforms import explore, monitor


def _record():
    return {
        "schema_version": "1.0.0",
        "source_url": "synthetic://record/1",
        "source": {
            "platform": "synthetic",
            "author": "research-fixture",
            "country": "FI",
            "language": "en",
            "created_at": "2026-01-01T12:00:00Z",
        },
        "content": {
            "text": "synthetic source text",
            "transcripts": [{"id": "t1", "text": "synthetic transcript"}],
            "ocr": [{"id": "o1", "text": "synthetic OCR"}],
            "frames": [{"id": "f1", "timestamp_seconds": 1.0, "description": "synthetic frame"}],
        },
        "analysis": {
            "status": "complete",
            "completed_at": "2026-01-01T13:00:00Z",
            "summary": "synthetic human-readable summary",
            "entities": [{"entity_id": "e1", "label": "Synthetic Actor"}],
            "topics": [{"label": "Synthetic Topic"}],
            "formations": [{"object_id": "fo1", "label": "Synthetic Formation", "kind": "formation"}],
            "signifiers": [{"object_id": "s1", "label": "future", "kind": "signifier"}],
            "discourses": [{"object_id": "d1", "label": "Synthetic Discourse", "kind": "discourse"}],
            "relations": [
                {
                    "relation_id": "r1",
                    "relation_type": "equivalence",
                    "source_ref": "future",
                    "target_ref": "Synthetic Actor",
                }
            ],
            "uncertainty": ["synthetic uncertainty"],
            "abstentions": [],
        },
        "provenance": [{"method": "synthetic-test", "created_at": "2026-01-01T13:00:00Z"}],
        "review": {"status": "PROVISIONAL"},
    }


def test_synthetic_canonical_monitor_explore_review_flow(tmp_path):
    source = tmp_path / "synthetic.jsonl"
    source.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
    frame = load_frame(source)

    assert frame.iloc[0]["source_url"] == "synthetic://record/1"
    assert frame.iloc[0]["transcript"] == "synthetic transcript"
    assert frame.iloc[0]["ocr"] == ["synthetic OCR"]
    assert frame.iloc[0]["formations"] == ["Synthetic Formation"]

    filtered = filter_frame(frame, countries=["FI"], formations=["Synthetic Formation"])
    assert len(filtered) == 1
    assert monitor(filtered)["analyzed"] == 1
    views = explore(filtered)
    assert views["formations"].iloc[0]["formations"] == "Synthetic Formation"
    assert views["relations"].iloc[0]["type"] == "equivalence"

    store = SQLiteReviewStore(tmp_path / "reviews.sqlite3")
    store.save(
        Review(
            source_url="synthetic://record/1",
            status="REVISED",
            corrections={"entities": ["Corrected Synthetic Actor"]},
            rerun_ocr=True,
        )
    )
    saved = store.get("synthetic://record/1")
    assert saved is not None
    assert saved.corrections["entities"] == ["Corrected Synthetic Actor"]
    assert saved.rerun_ocr is True
