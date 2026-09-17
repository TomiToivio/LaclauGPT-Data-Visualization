from __future__ import annotations

from laclaugpt_visualization.interop_dashboard import (
    dats_dashboard_frame,
    evidence_drilldown,
    graph_measure_table,
    graph_projection_view,
)


def test_dats_objects_map_to_normal_dashboard_dataframe() -> None:
    frame = dats_dashboard_frame(
        {
            "project_id": "dats-fi",
            "documents": [
                {
                    "id": "d1",
                    "source_url": "https://example.org/ääni",
                    "title": "Ääni",
                    "text": "tekoäly ja demokratia",
                    "language": "fi",
                }
            ],
            "annotations": [
                {
                    "id": "a1",
                    "document_id": "d1",
                    "code_id": "c1",
                    "producer_type": "model",
                    "producer_id": "gemma",
                    "confidence": 0.7,
                }
            ],
            "notes": [{"id": "n1", "text": "muistio"}],
        }
    )
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["source_platform"] == "dats"
    assert row["source_language"] == "fi"
    assert row["external_ids"] == {"dats": "d1"}
    assert row["review_status"] == "PROVISIONAL"
    assert bool(row["machine_generated"]) is True
    assert row["evidence"][0]["external_ids"] == {"dats": "a1"}


def _projection() -> dict:
    return {
        "projection_id": "conflict-1",
        "graph_type": "actor_conflict",
        "node_semantics": "actors",
        "edge_semantics": "precomputed disagreement relation",
        "projection_method": "DNA conflict projection",
        "weighting_method": "upstream normalized conflict weight",
        "temporal_scope": {"start": "2026-09-01", "end": "2026-09-17"},
        "filters": {"formation": "critical-ai"},
        "producer": {"id": "laclaugpt-data-analysis", "version": "0.2"},
        "source_analysis_run": "run-1",
        "provenance_id": "prov-1",
        "nodes": [
            {
                "id": "a1",
                "label": "Tutkija Ω",
                "node_type": "actor",
                "external_ids": {"dna": "actor-7"},
                "review_status": "ACCEPTED",
            },
            {"id": "a2", "label": "Toimija B", "node_type": "actor"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "a1",
                "target": "a2",
                "edge_type": "conflict",
                "weight": 0.8,
                "uncertainty": "low",
                "review_status": "PROVISIONAL",
                "evidence": [
                    {
                        "source_url": "https://example.org/source",
                        "evidence_id": "ev-1",
                        "statement_id": "s-1",
                        "external_ids": {"dna": "statement-9"},
                    }
                ],
            }
        ],
        "network_measures": [
            {"element_id": "a1", "degree": 3, "community": 2},
        ],
    }


def test_generic_projection_consumes_upstream_network_without_reanalysis() -> None:
    view = graph_projection_view(_projection())
    assert view.graph_type == "actor_conflict"
    assert view.projection_method == "DNA conflict projection"
    assert view.weighting_method == "upstream normalized conflict weight"
    assert view.filters == {"formation": "critical-ai"}
    assert view.temporal_scope["end"] == "2026-09-17"
    assert view.nodes[0].label == "Tutkija Ω"
    assert view.edges[0].weight == 0.8
    assert view.edges[0].uncertainty == "low"


def test_measure_table_only_exposes_precomputed_measures() -> None:
    table = graph_measure_table(_projection())
    assert table.to_dict(orient="records") == [
        {"element_id": "a1", "degree": 3, "community": 2}
    ]


def test_graph_selection_drills_down_to_evidence_and_provenance() -> None:
    detail = evidence_drilldown(graph_projection_view(_projection()), "e1")
    assert detail["projection_id"] == "conflict-1"
    assert detail["source_analysis_run"] == "run-1"
    assert detail["provenance_id"] == "prov-1"
    assert detail["review_status"] == "PROVISIONAL"
    assert detail["evidence"][0]["source_url"] == "https://example.org/source"
    assert detail["evidence"][0]["external_ids"]["dna"] == "statement-9"
    assert "community/cluster != ideological formation" in detail["safeguards"]
