from __future__ import annotations

import pandas as pd

from laclaugpt_visualization.spatiotemporal import (
    spatiotemporal_map_points,
    spatiotemporal_timeline,
    spatiotemporal_timeline_counts,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_url": "synthetic://phase1/one",
                "source_author": "Synthetic Actor",
                "summary": "Synthetic record",
                "source_timestamp": "2026-09-16T10:00:00Z",
                "collection_timestamp": "2026-09-16T10:05:00Z",
                "analysis_timestamp": "2026-09-16T11:00:00Z",
                "review_status": "ACCEPTED",
                "raw_record": {
                    "source": {
                        "locations": [
                            {
                                "location_id": "src-helsinki",
                                "name": "Helsinki",
                                "latitude": 60.1699,
                                "longitude": 24.9384,
                                "coordinate_method": "source-provided",
                                "evidence_refs": ["source-location"],
                            }
                        ]
                    },
                    "analysis": {
                        "locations": [
                            {
                                "location_id": "validated-espoo",
                                "name": "Espoo",
                                "latitude": 60.2055,
                                "longitude": 24.6559,
                                "coordinate_method": "geocoded",
                                "validation_status": "human-validated",
                                "evidence_refs": ["analysis-location"],
                            },
                            {
                                "location_id": "geocoded-no-review",
                                "name": "Vantaa",
                                "latitude": 60.2934,
                                "longitude": 25.0378,
                                "coordinate_method": "geocoded",
                                "evidence_refs": ["analysis-location-2"],
                            },
                            {
                                "location_id": "inferred",
                                "name": "Tampere",
                                "latitude": 61.4978,
                                "longitude": 23.7610,
                                "coordinate_method": "inferred",
                                "evidence_refs": ["analysis-location-3"],
                            },
                            {
                                "location_id": "missing-evidence",
                                "name": "Turku",
                                "latitude": 60.4518,
                                "longitude": 22.2666,
                                "coordinate_method": "source-provided",
                            },
                            {
                                "location_id": "partial",
                                "name": "Oulu",
                                "latitude": 65.0121,
                                "coordinate_method": "source-provided",
                                "evidence_refs": ["analysis-location-4"],
                            },
                        ],
                        "events": [
                            {
                                "event_name": "Evidence-backed event",
                                "event_date": "2026-09-15",
                                "event_type": "hearing",
                                "evidence_refs": ["event-1"],
                            },
                            {
                                "event_name": "Missing time",
                                "evidence_refs": ["event-2"],
                            },
                            {
                                "event_name": "Missing evidence",
                                "event_date": "2026-09-14",
                            },
                        ],
                    },
                },
            },
            {
                "source_url": "synthetic://phase1/two",
                "source_timestamp": None,
                "collection_timestamp": "not-a-date",
                "analysis_timestamp": None,
                "raw_record": {"analysis": {"locations": [], "events": []}},
            },
        ]
    )


def test_phase1_timeline_keeps_clocks_separate_and_never_substitutes() -> None:
    timeline = spatiotemporal_timeline(_frame())

    first = timeline[timeline["source_url"] == "synthetic://phase1/one"]
    assert set(first["time_kind"]) == {"source", "collection", "analysis", "event"}
    assert (
        first[first["time_kind"] == "source"].iloc[0]["timestamp"]
        == pd.Timestamp("2026-09-16T10:00:00Z")
    )
    assert (
        first[first["time_kind"] == "collection"].iloc[0]["timestamp"]
        == pd.Timestamp("2026-09-16T10:05:00Z")
    )
    event = first[first["time_kind"] == "event"].iloc[0]
    assert event["label"] == "Evidence-backed event"
    assert event["evidence_refs"] == ["event-1"]

    second = timeline[timeline["source_url"] == "synthetic://phase1/two"]
    assert second.empty


def test_phase1_timeline_counts_are_deterministic_and_clock_specific() -> None:
    counts = spatiotemporal_timeline_counts(_frame())
    assert counts.to_dict(orient="records") == [
        {
            "period": pd.Timestamp("2026-09-15T00:00:00Z"),
            "time_kind": "event",
            "documents": 1,
        },
        {
            "period": pd.Timestamp("2026-09-16T00:00:00Z"),
            "time_kind": "analysis",
            "documents": 1,
        },
        {
            "period": pd.Timestamp("2026-09-16T00:00:00Z"),
            "time_kind": "collection",
            "documents": 1,
        },
        {
            "period": pd.Timestamp("2026-09-16T00:00:00Z"),
            "time_kind": "source",
            "documents": 1,
        },
    ]


def test_phase1_map_disables_inferred_partial_and_unsupported_geography() -> None:
    points = spatiotemporal_map_points(_frame())

    assert points["location"].tolist() == ["Helsinki", "Espoo"]
    assert points["coordinate_status"].tolist() == [
        "source-provided",
        "human-validated",
    ]
    assert points["evidence_refs"].tolist() == [
        ["source-location"],
        ["analysis-location"],
    ]
    assert set(points["source_url"]) == {"synthetic://phase1/one"}


def test_phase1_spatiotemporal_empty_states_are_stable() -> None:
    empty = pd.DataFrame()
    assert spatiotemporal_timeline(empty).empty
    assert spatiotemporal_timeline_counts(empty).empty
    assert spatiotemporal_map_points(empty).empty
