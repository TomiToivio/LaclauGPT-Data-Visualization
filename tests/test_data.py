from __future__ import annotations

import pandas as pd

from laclaugpt_visualization.data import explode_labels, filter_frame, frame_from_records, normalize_frame


def test_normalize_frame_parses_list_columns() -> None:
    frame = pd.DataFrame(
        [
            {
                "document_id": "doc-1",
                "source_platform": "x",
                "summary": "AI politics",
                "topics": '["AI", "policy"]',
                "signifiers": "AGI; safety",
            }
        ]
    )
    normalized = normalize_frame(frame)
    assert normalized.loc[0, "topics"] == ["AI", "policy"]
    assert normalized.loc[0, "signifiers"] == ["AGI", "safety"]
    assert "AI politics" in normalized.loc[0, "searchable_text"]


def test_explode_labels_counts_values() -> None:
    frame = normalize_frame(
        pd.DataFrame(
            [
                {"document_id": "1", "topics": ["AI", "policy"]},
                {"document_id": "2", "topics": ["AI"]},
            ]
        )
    )
    counts = explode_labels(frame, "topics")
    assert counts.iloc[0].to_dict() == {"topics": "AI", "count": 2}


def test_filter_frame_uses_search_and_platform() -> None:
    frame = normalize_frame(
        pd.DataFrame(
            [
                {"document_id": "1", "summary": "Acceleration", "source_platform": "x"},
                {"document_id": "2", "summary": "Critical AI", "source_platform": "bluesky"},
            ]
        )
    )
    result = filter_frame(frame, query="critical", platforms=["bluesky"])
    assert result["document_id"].tolist() == ["2"]



def _canonical_analysis_record() -> dict:
    return {
        "schema_version": "1.1.0",
        "source_url": "https://example.test/analyzed",
        "source": {"platform": "web", "author": "fixture"},
        "content": {"text": "Analyzed source text"},
        "analysis": {
            "status": "analyzed",
            "formations": [{"label": "corporate concentration"}],
            "entities": [{"label": "European Union"}, {"label": "Google"}],
            "signifiers": [{"label": "competition"}],
            "claims": [{"text": "Synthetic claim"}],
        },
        "review": {"status": "VERIFIED"},
        "provenance": [{"method": "synthetic-analysis"}],
    }


def test_frame_from_records_unwraps_analysis_result_envelope() -> None:
    canonical = _canonical_analysis_record()
    envelope = {
        "_id": "mongo-only-id",
        "project_id": "ai26",
        "run_id": "run-1",
        "source_url": canonical["source_url"],
        "result": canonical,
        "provenance": [{"method": "envelope-fallback"}],
        "created_at": 1_795_000_000.0,
    }

    frame = frame_from_records([envelope])
    row = frame.iloc[0]

    assert row["source_url"] == canonical["source_url"]
    assert row["schema_version"] == "1.1.0"
    assert row["analysis_status"] == "analyzed"
    assert row["formations"] == ["corporate concentration"]
    assert row["entities"] == ["European Union", "Google"]
    assert row["signifiers"] == ["competition"]
    assert row["review_status"] == "VERIFIED"
    assert row["raw_record"]["analysis"]["claims"] == [{"text": "Synthetic claim"}]
    assert row["raw_record"]["provenance"] == [{"method": "synthetic-analysis"}]


def test_frame_from_records_keeps_flat_and_unanalysed_shapes_readable() -> None:
    canonical = _canonical_analysis_record()
    flat = frame_from_records([canonical]).iloc[0]
    assert flat["analysis_status"] == "analyzed"
    assert flat["review_status"] == "VERIFIED"

    awaiting = frame_from_records(
        [
            {
                "schema_version": "1.1.0",
                "source_url": "https://example.test/awaiting",
                "source": {"platform": "web"},
                "content": {"text": "Awaiting analysis"},
                "analysis": {},
                "review": {},
            }
        ]
    ).iloc[0]
    assert awaiting["analysis_status"] == "collection-only"
    assert awaiting["formations"] == []
    assert awaiting["entities"] == []
    assert awaiting["review_status"] == "PROVISIONAL"


def test_result_envelope_uses_envelope_fallback_metadata() -> None:
    canonical = _canonical_analysis_record()
    canonical.pop("source_url")
    canonical.pop("provenance")
    frame = frame_from_records(
        [
            {
                "source_url": "https://example.test/fallback",
                "result": canonical,
                "provenance": [{"method": "outer-envelope"}],
                "created_at": 1_795_000_000.0,
            }
        ]
    )
    row = frame.iloc[0]
    assert row["source_url"] == "https://example.test/fallback"
    assert row["raw_record"]["provenance"] == [{"method": "outer-envelope"}]
    assert row["raw_record"]["created_at"] == 1_795_000_000.0
