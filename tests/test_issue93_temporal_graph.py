from __future__ import annotations

import pandas as pd
import pytest

from laclaugpt_visualization.temporal_graph import temporal_graph_projection, temporal_window


def _frame() -> pd.DataFrame:
    def record(
        suffix: str,
        source_time: str,
        collection_time: str,
        analysis_time: str,
        source: str,
        target: str,
    ) -> dict[str, object]:
        url = f"synthetic://temporal/{suffix}"
        return {
            "source_url": url,
            "document_id": url,
            "source_author": source,
            "source_timestamp": source_time,
            "collection_timestamp": collection_time,
            "analysis_timestamp": analysis_time,
            "review_status": "ACCEPTED",
            "entities": [target],
            "signifiers": [target],
            "topics": [],
            "formations": [],
            "relations": [
                {
                    "source_ref": source,
                    "target_ref": target,
                    "relation_type": "articulates",
                    "validation_status": "human-validated",
                    "evidence_refs": [f"e-{suffix}"],
                }
            ],
        }

    return pd.DataFrame(
        [
            record(
                "a",
                "2026-09-01T10:00:00Z",
                "2026-09-01T12:00:00Z",
                "2026-09-02T09:00:00Z",
                "Actor A",
                "Signifier X",
            ),
            record(
                "b",
                "2026-09-03T10:00:00Z",
                "2026-09-03T12:00:00Z",
                "2026-09-04T09:00:00Z",
                "Actor B",
                "Signifier Y",
            ),
            record(
                "missing-source",
                "",
                "2026-09-05T12:00:00Z",
                "2026-09-06T09:00:00Z",
                "Actor C",
                "Signifier Z",
            ),
        ]
    )


def test_temporal_window_boundaries_are_inclusive_and_missing_is_explicit() -> None:
    window, metadata = temporal_window(
        _frame(),
        clock="source",
        start="2026-09-01T10:00:00Z",
        end="2026-09-03T10:00:00Z",
    )
    assert window["source_url"].tolist() == [
        "synthetic://temporal/a",
        "synthetic://temporal/b",
    ]
    assert metadata["records_missing_timestamp"] == 1
    assert metadata["records_in_window"] == 2
    assert metadata["timestamp_field"] == "source_timestamp"


def test_clocks_are_not_conflated() -> None:
    source_window, _ = temporal_window(
        _frame(),
        clock="source",
        start="2026-09-05T00:00:00Z",
        end="2026-09-07T00:00:00Z",
    )
    collection_window, _ = temporal_window(
        _frame(),
        clock="collection",
        start="2026-09-05T00:00:00Z",
        end="2026-09-07T00:00:00Z",
    )
    assert source_window.empty
    assert collection_window["source_url"].tolist() == ["synthetic://temporal/missing-source"]


@pytest.mark.parametrize("clock", ["source", "collection", "analysis"])
def test_temporal_graph_is_bounded_traceable_and_deterministic(clock: str) -> None:
    frame = _frame()
    forward = temporal_graph_projection(frame, clock=clock, max_nodes=2, max_edges=1)
    reverse = temporal_graph_projection(
        frame.iloc[::-1].reset_index(drop=True),
        clock=clock,
        max_nodes=2,
        max_edges=1,
    )

    assert forward == reverse
    assert 1 <= len(forward["nodes"]) <= 2
    assert len(forward["edges"]) == 1
    assert forward["truncated"] is True
    edge = forward["edges"][0]
    assert edge["source_urls"]
    assert edge["evidence_refs"]
    assert edge["clock"] == clock
    assert edge["timestamp_field"] == f"{clock}_timestamp"
    assert edge["timestamps"] == sorted(edge["timestamps"])


def test_temporal_graph_disables_when_selected_clock_has_no_explicit_timestamps() -> None:
    frame = _frame().copy()
    frame["analysis_timestamp"] = ""
    result = temporal_graph_projection(frame, clock="analysis")
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["temporal"]["supported"] is False
    assert result["temporal"]["records_missing_timestamp"] == len(frame)


def test_invalid_window_and_limits_fail_closed() -> None:
    with pytest.raises(ValueError):
        temporal_window(
            _frame(),
            clock="source",
            start="2026-09-04T00:00:00Z",
            end="2026-09-01T00:00:00Z",
        )
    with pytest.raises(ValueError):
        temporal_graph_projection(_frame(), max_edges=0)
