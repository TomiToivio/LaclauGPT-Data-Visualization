from copy import deepcopy

import pytest

from laclaugpt_visualization.data import frame_from_records
from laclaugpt_visualization.review import (
    Review,
    SQLiteReviewStore,
    canonical_review_source_url,
    save_canonical_review,
)


def _canonical_record():
    return {
        "schema_version": "1.0.0",
        "source_url": "synthetic://canonical/80",
        "source": {"platform": "synthetic", "author": "researcher"},
        "content": {"text": "source evidence"},
        "analysis": {
            "status": "complete",
            "summary": "analysis remains immutable",
            "entities": [{"label": "Synthetic Actor"}],
        },
        "provenance": [{"method": "synthetic"}],
    }


def test_issue80_canonical_review_roundtrip_preserves_all_request_fields(tmp_path):
    source = _canonical_record()
    frame = frame_from_records([source])
    row = frame.iloc[0].to_dict()
    assert canonical_review_source_url(row) == source["source_url"]

    store = SQLiteReviewStore(tmp_path / "reviews.sqlite3")
    review = Review(
        source_url=source["source_url"],
        reviewer="synthetic-reviewer",
        status="REVISED",
        dubious=True,
        exclude=True,
        wrong_language=True,
        note="Check entity normalization.",
        corrections={
            "entities": ["Corrected Actor"],
            "summary": "Researcher correction",
        },
        rerun_analysis=True,
        rerun_asr=True,
        rerun_ocr=True,
        reprocess_media=True,
        split_request={"at_seconds": [10.5, 23.0]},
        cut_request={"start_seconds": 2.0, "end_seconds": 18.0},
        review_version=4,
    )

    save_canonical_review(row, review, store)
    saved = store.get(source["source_url"])

    assert saved is not None
    assert saved.model_dump(exclude={"updated_at"}) == review.model_dump(
        exclude={"updated_at"}
    )


def test_issue80_review_write_does_not_mutate_canonical_analysis(tmp_path):
    source = _canonical_record()
    before = deepcopy(source)
    store = SQLiteReviewStore(tmp_path / "reviews.sqlite3")

    save_canonical_review(
        source,
        Review(
            source_url=source["source_url"],
            status="ACCEPTED",
            corrections={"entities": ["Human correction"]},
            rerun_analysis=True,
        ),
        store,
    )

    assert source == before
    assert source["analysis"] == before["analysis"]
    assert "review" not in source


def test_issue80_phase0_and_legacy_rows_are_not_reviewable(tmp_path):
    phase0 = {
        "source_url": "synthetic://phase0/80",
        "phase0_summary": {"summary": "Phase 0"},
        "phase0": {"summary": {"status": "ok"}},
    }
    phase0_row = frame_from_records([phase0]).iloc[0].to_dict()
    assert canonical_review_source_url(phase0_row) is None

    legacy = {
        "source_url": "legacy:ep24:80",
        "document_id": "legacy:ep24:80",
        "summary": "legacy only",
    }
    assert canonical_review_source_url(legacy) is None

    store = SQLiteReviewStore(tmp_path / "reviews.sqlite3")
    with pytest.raises(ValueError, match="canonical Phase 1"):
        save_canonical_review(
            phase0_row,
            Review(source_url="synthetic://phase0/80"),
            store,
        )
    assert store.get("synthetic://phase0/80") is None


def test_issue80_review_identity_must_match_canonical_source_url(tmp_path):
    source = _canonical_record()
    store = SQLiteReviewStore(tmp_path / "reviews.sqlite3")

    with pytest.raises(ValueError, match="must match"):
        save_canonical_review(
            source,
            Review(source_url="synthetic://different"),
            store,
        )

    assert store.get("synthetic://different") is None
