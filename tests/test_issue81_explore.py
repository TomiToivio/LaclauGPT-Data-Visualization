from __future__ import annotations

import pandas as pd
import pytest

from laclaugpt_visualization.transforms import explore, timeline


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_timestamp": "2026-09-01T10:00:00Z",
                "collection_timestamp": "2026-09-02T10:00:00Z",
                "analysis_timestamp": "2026-09-03T10:00:00Z",
                "formations": ["accelerationism", "ai critical"],
                "topics": ["governance", "compute"],
                "entities": ["Actor A"],
                "signifiers": ["safety", "abundance"],
                "relations": [],
            },
            {
                "source_timestamp": "2026-09-01T20:00:00Z",
                "collection_timestamp": "2026-09-04T10:00:00Z",
                "analysis_timestamp": "",
                "formations": ["ai critical"],
                "topics": ["governance"],
                "entities": ["Actor B"],
                "signifiers": ["safety"],
                "relations": [],
            },
        ]
    )


def test_timeline_uses_one_explicit_clock_without_fallback() -> None:
    frame = _frame()

    source = timeline(frame, clock="source")
    collection = timeline(frame, clock="collection")
    analysis = timeline(frame, clock="analysis")

    assert source["documents"].tolist() == [2]
    assert collection["documents"].tolist() == [1, 1]
    assert analysis["documents"].tolist() == [1]
    assert source["period"].dt.day.tolist() == [1]
    assert collection["period"].dt.day.tolist() == [2, 4]
    assert analysis["period"].dt.day.tolist() == [3]


def test_explore_preserves_multi_label_overlap_and_signifiers() -> None:
    views = explore(_frame())

    formations = views["formations"].set_index("formations")["count"].to_dict()
    signifiers = views["signifiers"].set_index("signifiers")["count"].to_dict()

    assert formations["ai critical"] == 2
    assert formations["accelerationism"] == 1
    assert signifiers["safety"] == 2
    assert signifiers["abundance"] == 1


def test_explore_empty_and_missing_clock_states_are_deterministic() -> None:
    empty = explore(pd.DataFrame(), timeline_clock="analysis")
    assert empty["timeline"].empty
    assert empty["formations"].empty
    assert empty["signifiers"].empty

    missing = timeline(\n        pd.DataFrame([{"source_timestamp": "2026-09-01T00:00:00Z"}]),\n        clock="analysis",\n    )
    assert missing.empty


def test_timeline_rejects_unknown_clock() -> None:
    with pytest.raises(ValueError, match="clock must be one of"):
        timeline(_frame(), clock="event")
