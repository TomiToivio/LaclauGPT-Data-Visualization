from __future__ import annotations

import pandas as pd
import pytest

from laclaugpt_visualization.graph_explorer import projection_envelope
from laclaugpt_visualization.transforms import relations, temporal_graph_projection


def _temporal_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "document_id": "doc-a",
                "source_url": "synthetic://temporal/a",
                "source_timestamp": "2026-09-20T10:00:00Z",
                "collection_timestamp": "2026-09-20T12:00:00Z",
                "analysis_timestamp": "2026-09-20T14:00:00Z",
                "review_status": "ACCEPTED",
                "relations": [
                    {
                        "source_ref": "actor-a",
                        "target_ref": "signifier-a",
                        "relation_type": "uses_signifier",
                        "evidence_refs": ["e-a"],
                    }
                ],
            },
            {
                "document_id": "doc-b",
                "source_url": "synthetic://temporal/b",
                "source_timestamp": "2026-09-20T11:00:00Z",
                "collection_timestamp": "2026-09-20T13:00:00Z",
                "analysis_timestamp": "2026-09-20T15:00:00Z",
                "review_status": "PROVISIONAL",
                "relations": [
                    {
                        "source_ref": "actor-b",
                        "target_ref": "signifier-b",
                        "relation_type": "uses_signifier",
                        "evidence_refs": ["e-b"],
                    }
                ],
            },
            {
                "document_id": "doc-c",
                "source_url": "synthetic://temporal/c",
                "source_timestamp": "2026-09-20T12:00:00Z",
                "collection_timestamp": None,
                "analysis_timestamp": "2026-09-20T16:00:00Z",
                "review_status": "PROVISIONAL",
                "relations": [
                    {
                        "source_ref": "actor-c",
                        "target_ref": "signifier-c",
                        "relation_type": "uses_signifier",
                        "evidence_refs": ["e-c"],
                    }
                ],
            },
        ]
    )


def test_relations_preserve_all_three_recorded_clocks() -> None:
    table = relations(_temporal_frame())
    first = table[table["source_url"] == "synthetic://temporal/a"].iloc[0]
    assert first["source_timestamp"] == "2026-09-20T10:00:00Z"
    assert first["collection_timestamp"] == "2026-09-20T12:00:00Z"
    assert first["analysis_timestamp"] == "2026-09-20T14:00:00Z"


def test_temporal_window_boundaries_are_inclusive_and_clock_specific() -> None:
    source = temporal_graph_projection(
        _temporal_frame(),
        clock="source",
        start="2026-09-20T10:00:00Z",
        end="2026-09-20T11:00:00Z",
    )
    assert {edge["source_urls"][0] for edge in source["edges"]} == {
        "synthetic://temporal/a",
        "synthetic://temporal/b",
    }
    assert source["temporal"]["records_in_window"] == 2
    assert source["temporal"]["clock"] == "source"

    collection = temporal_graph_projection(
        _temporal_frame(),
        clock="collection",
        start="2026-09-20T10:00:00Z",
        end="2026-09-20T11:00:00Z",
    )
    assert collection["edges"] == []
    assert collection["temporal"]["records_missing_timestamp"] == 1


def test_temporal_projection_is_bounded_and_deterministic() -> None:
    frame = _temporal_frame()
    first = temporal_graph_projection(
        frame,
        clock="source",
        max_edges=1,
        max_nodes=2,
    )
    second = temporal_graph_projection(
        frame.iloc[::-1],
        clock="source",
        max_edges=1,
        max_nodes=2,
    )
    assert first == second
    assert len(first["edges"]) <= 1
    assert len(first["nodes"]) <= 2
    assert first["bounded"] is True


def test_temporal_edges_remain_traceable_to_evidence_and_clock_values() -> None:
    projection = temporal_graph_projection(
        _temporal_frame(),
        clock="analysis",
        start="2026-09-20T14:00:00Z",
        end="2026-09-20T14:00:00Z",
    )
    assert len(projection["edges"]) == 1
    edge = projection["edges"][0]
    assert edge["source_urls"] == ["synthetic://temporal/a"]
    assert edge["evidence_refs"] == ["e-a"]
    assert edge["source_timestamps"] == ["2026-09-20T10:00:00Z"]
    assert edge["collection_timestamps"] == ["2026-09-20T12:00:00Z"]
    assert edge["analysis_timestamps"] == ["2026-09-20T14:00:00Z"]


def test_projection_envelope_exposes_temporal_contract_metadata() -> None:
    graph = projection_envelope(
        _temporal_frame(),
        clock="analysis",
        start="2026-09-20T14:00:00Z",
        end="2026-09-20T15:00:00Z",
    )
    assert graph.metadata["temporal"]["clock"] == "analysis"
    assert graph.metadata["temporal"]["timestamp_column"] == "analysis_timestamp"
    assert graph.metadata["temporal"]["records_in_window"] == 2


@pytest.mark.parametrize("clock", ["event", "timestamp", ""])
def test_temporal_projection_rejects_unknown_clock(clock: str) -> None:
    with pytest.raises(ValueError, match="clock must be one of"):
        temporal_graph_projection(_temporal_frame(), clock=clock)


def test_temporal_projection_rejects_reversed_window() -> None:
    with pytest.raises(ValueError, match="start timestamp"):
        temporal_graph_projection(
            _temporal_frame(),
            clock="source",
            start="2026-09-20T12:00:00Z",
            end="2026-09-20T10:00:00Z",
        )
