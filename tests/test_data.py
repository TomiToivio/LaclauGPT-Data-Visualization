from __future__ import annotations

import pandas as pd

from laclaugpt_visualization.data import explode_labels, filter_frame, normalize_frame


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
