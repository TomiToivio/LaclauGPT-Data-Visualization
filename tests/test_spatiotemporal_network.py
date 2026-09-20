from __future__ import annotations

import pandas as pd

from laclaugpt_visualization.research_views import discourse_timeline, map_points, timeline_events
from laclaugpt_visualization.transforms import graph_projection, relations


def _frame() -> pd.DataFrame:
    record = {
        "source_url": "synthetic://record/1",
        "document_id": "synthetic://record/1",
        "source_author": "Synthetic Actor",
        "source_type": "post",
        "source_timestamp": "2026-09-16T10:00:00Z",
        "analysis_timestamp": "2026-09-16T11:00:00Z",
        "review_status": "ACCEPTED",
        "human_readable_summary": "Synthetic research summary",
        "entities": ["Helsinki", "Public AI"],
        "signifiers": ["public AI", "abundance"],
        "topics": ["infrastructure"],
        "formations": ["public-interest techno-optimism"],
        "relations": [
            {
                "source_ref": "Synthetic Actor",
                "target_ref": "public AI",
                "relation_type": "uses_signifier",
                "weight": 2,
                "validation_status": "human-validated",
                "evidence_refs": ["e1"],
            },
            {
                "source_ref": "public AI",
                "target_ref": "abundance",
                "relation_type": "articulated_with",
                "origin": "inferred",
                "evidence_refs": ["e2"],
            },
        ],
        "provenance": [{"stage": "analysis", "method": "synthetic"}],
        "raw_record": {
            "analysis": {
                "locations": [
                    {
                        "location_id": "loc-hel",
                        "name": "Helsinki",
                        "latitude": 60.1699,
                        "longitude": 24.9384,
                        "coordinate_method": "source-provided",
                        "evidence_refs": ["e-location-1"],
                    },
                    {
                        "location_id": "loc-espoo",
                        "name": "Espoo",
                        "latitude": 60.2055,
                        "longitude": 24.6559,
                        "coordinate_method": "geocoded",
                    },
                    {
                        "location_id": "loc-ambiguous",
                        "name": "Springfield",
                        "latitude": 39.0,
                        "longitude": -89.0,
                        "resolved": False,
                        "ambiguity": "multiple candidate cities",
                    },
                ],
                "events": [
                    {
                        "event_name": "Public AI hearing",
                        "event_date": "2026-09-15",
                        "event_type": "hearing",
                        "description": "Synthetic event",
                        "validation_status": "human-validated",
                        "evidence_refs": ["e-event-1"],
                    }
                ],
            }
        },
    }
    return pd.DataFrame([record])


def test_map_supports_multiple_locations_and_omits_unresolved_ambiguity() -> None:
    points = map_points(_frame())
    assert points["location"].tolist() == ["Helsinki", "Espoo"]
    assert points["coordinate_status"].tolist() == ["source-provided", "geocoded"]
    assert points.iloc[0]["source_url"] == "synthetic://record/1"
    assert points.iloc[0]["evidence_refs"] == ["e-location-1"]


def test_timeline_preserves_event_evidence_and_record_clocks() -> None:
    events = timeline_events(_frame())
    assert {"source", "analysis", "event"}.issubset(set(events["time_kind"]))
    extracted = events[events["label"] == "Public AI hearing"].iloc[0]
    assert extracted["source_url"] == "synthetic://record/1"
    assert extracted["evidence_refs"] == ["e-event-1"]
    assert extracted["review_status"] == "human-validated"


def test_discourse_timeline_exposes_actor_entity_signifier_topic_and_formation() -> None:
    timeline = discourse_timeline(_frame())
    assert set(timeline["dimension"]) == {"actor", "entity", "signifier", "topic", "formation"}
    public_ai = timeline[(timeline["dimension"] == "signifier") & (timeline["label"] == "public AI")].iloc[0]
    assert public_ai["count"] == 1
    assert public_ai["source_urls"] == ["synthetic://record/1"]


def test_network_projection_keeps_evidence_validation_and_size_bound() -> None:
    frame = _frame()
    edges = relations(frame)
    assert edges.iloc[0]["edge_status"] == "human-reviewed"
    assert edges.iloc[0]["validation_status"] == "human-reviewed"
    assert edges.iloc[0]["evidence_refs"] == ["e1"]

    projection = graph_projection(frame, max_edges=1)
    assert len(projection["edges"]) == 1
    edge = projection["edges"][0]
    assert edge["source_urls"] == ["synthetic://record/1"]
    assert edge["evidence_refs"] == ["e1"]
    assert edge["edge_status"] == "human-reviewed"
    assert {node["id"] for node in projection["nodes"]} == {"Synthetic Actor", "public AI"}


def test_network_projection_enforces_strict_node_edge_bounds_and_reports_truncation() -> None:
    frame = _frame()
    frame.at[0, "relations"] = [
        *frame.at[0, "relations"],
        {
            "source_ref": "abundance",
            "target_ref": "infrastructure",
            "relation_type": "articulated_with",
            "evidence_refs": ["e3"],
        },
    ]

    projection = graph_projection(frame, max_nodes=2, max_edges=2)

    assert len(projection["nodes"]) <= 2
    assert len(projection["edges"]) <= 2
    assert projection["truncated"] is True
    assert projection["limits"] == {"nodes": 2, "edges": 2}

    zero = graph_projection(frame, max_nodes=0, max_edges=0)
    assert zero["nodes"] == []
    assert zero["edges"] == []
    assert zero["truncated"] is True
    assert zero["limits"] == {"nodes": 0, "edges": 0}


def test_network_projection_handles_malformed_relations_without_losing_traceability() -> None:
    frame = _frame()
    frame.at[0, "relations"] = [
        {
            "source_ref": "Synthetic Actor",
            "target_ref": "public AI",
            "relation_type": "uses_signifier",
            "weight": "not-a-number",
            "validation_status": "human-validated",
            "evidence_refs": ["e-bad-weight"],
        },
        {"source_ref": "", "target_ref": "ignored", "weight": {}},
        "not-a-relation-object",
    ]

    projection = graph_projection(frame)

    assert len(projection["edges"]) == 1
    edge = projection["edges"][0]
    assert edge["weight"] == 1.0
    assert edge["source_urls"] == ["synthetic://record/1"]
    assert edge["evidence_refs"] == ["e-bad-weight"]
    assert edge["edge_status"] == "human-reviewed"
