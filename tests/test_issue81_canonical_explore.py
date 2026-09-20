from __future__ import annotations

import pandas as pd

from laclaugpt_visualization.canonical_explore import canonical_explore


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_url": "https://example.invalid/a",
                "source_timestamp": "2026-09-14T10:00:00Z",
                "collection_timestamp": "2026-09-15T10:00:00Z",
                "analysis_timestamp": "2026-09-16T10:00:00Z",
                "event_date": "2026-09-13",
                "formations": ["critical-ai", "governance"],
                "topics": ["policy", "compute"],
                "entities": ["EU"],
                "signifiers": ["safety", "AGI"],
            },
            {
                "source_url": "https://example.invalid/b",
                "source_timestamp": "2026-09-14T12:00:00Z",
                "collection_timestamp": "2026-09-15T12:00:00Z",
                "analysis_timestamp": "2026-09-17T10:00:00Z",
                "formations": ["critical-ai"],
                "topics": ["policy"],
                "entities": ["EU", "OpenAI"],
                "signifiers": ["safety"],
            },
        ]
    )


def test_canonical_explore_preserves_distinct_timeline_clocks_and_source_identity() -> None:
    views = canonical_explore(_frame())
    timeline = views["timeline"]

    assert set(timeline["time_kind"]) == {"source", "collection", "analysis", "event"}
    source_day = timeline[
        (timeline["time_kind"] == "source")
        & (timeline["period"] == pd.Timestamp("2026-09-14", tz="UTC"))
    ].iloc[0]
    assert source_day["documents"] == 2
    assert source_day["source_urls"] == [
        "https://example.invalid/a",
        "https://example.invalid/b",
    ]


def test_canonical_explore_distributions_preserve_multilabel_overlap_deterministically() -> None:
    views = canonical_explore(_frame())

    assert views["formations"].iloc[0].to_dict() == {
        "formations": "critical-ai",
        "count": 2,
        "source_urls": [
            "https://example.invalid/a",
            "https://example.invalid/b",
        ],
    }
    assert views["signifiers"].iloc[0]["signifiers"] == "safety"

    overlap = views["formation_signifier"]
    pairs = {
        (row.formation, row.signifier): row.count
        for row in overlap.itertuples(index=False)
    }
    assert pairs[("critical-ai", "safety")] == 2
    assert pairs[("governance", "AGI")] == 1
    assert overlap.columns.tolist() == ["formation", "signifier", "count", "source_urls"]


def test_canonical_explore_empty_state_has_stable_schemas() -> None:
    views = canonical_explore(pd.DataFrame())

    assert views["timeline"].columns.tolist() == [
        "period",
        "time_kind",
        "documents",
        "source_urls",
    ]
    for field in ("formations", "topics", "entities", "signifiers"):
        assert views[field].columns.tolist() == [field, "count", "source_urls"]
        assert views[field].empty
    assert views["formation_signifier"].empty
