from __future__ import annotations

import csv
import io
import json
from xml.etree import ElementTree

from laclaugpt_visualization.interoperability import (
    SEMANTIC_SAFEGUARDS,
    dats_review_view,
    dna_graph_view,
    export_dats_review,
    gexf_dumps,
    graph_json,
    graphml_dumps,
    node_edge_csv,
    renderer_payload,
    vega_lite_spec,
)


def _dats() -> dict:
    return {
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
        "codes": [
            {"id": "c1", "canonical_id": "code:democracy", "label": "demokratia"},
        ],
        "annotations": [
            {
                "id": "a1",
                "document_id": "d1",
                "code_id": "code:democracy",
                "start": 11,
                "end": 20,
                "producer_type": "model",
                "producer_id": "gemma",
                "confidence": 0.72,
            },
            {
                "id": "a2",
                "document_id": "d1",
                "code_id": "code:democracy",
                "start": 11,
                "end": 20,
                "producer_type": "human",
                "producer_id": "researcher",
                "review_status": "ACCEPTED",
            },
        ],
        "notes": [{"id": "memo-1", "text": "research memo"}],
        "temporal_series": [{"series_id": "t1", "label": "demokratia", "points": []}],
        "relations": [{"id": "r1", "source": "c1", "target": "d1", "type": "mentions"}],
    }


def _statements() -> list[dict]:
    return [
        {
            "statement_id": "s1",
            "actor_id": "a:1",
            "actor_label": "Tutkija Ω",
            "concept_id": "c:1",
            "concept_label": "demokratia",
            "qualifier": "agreement",
            "source_url": "https://example.org/ääni",
            "source_document_id": "d1",
            "evidence_id": "ev1",
            "timestamp": "2026-09-17T10:00:00+00:00",
            "producer": {"type": "human", "id": "r1"},
            "confidence": 0.9,
            "uncertainty": "low",
            "review_status": "ACCEPTED",
            "external_ids": [{"system": "dna", "id": "dna-7"}],
        },
        {
            "statement_id": "s2",
            "actor_id": "a:2",
            "actor_label": "Model actor",
            "concept_id": "c:1",
            "concept_label": "demokratia",
            "qualifier": "disagreement",
            "source_url": "https://example.org/b",
            "source_document_id": "d2",
            "evidence_id": "ev2",
            "producer": {"type": "model", "id": "gemma4:12b"},
            "review_status": "PROVISIONAL",
            "uncertainty": "requires review",
            "external_ids": [{"system": "dna", "id": "dna-8"}],
        },
    ]


def _projection() -> dict:
    return {
        "projection_id": "p1",
        "graph_type": "actor_concept_bipartite",
        "node_semantics": "actor and concept nodes",
        "edge_semantics": "coded statements",
        "projection_method": "statement affiliation",
        "weighting_method": "statement count",
        "temporal_scope": {"start": "2026-09-17", "end": "2026-09-18"},
        "parameters": {"filters": {"arena": "elites"}},
        "producer": {"type": "tool", "id": "laclaugpt-data-analysis", "version": "0.1"},
        "provenance_id": "prov:1",
    }


def test_dats_view_preserves_external_ids_and_human_ai_status() -> None:
    view = dats_review_view(_dats())
    assert view["documents"][0]["external_ids"] == {"dats": "d1"}
    assert view["documents"][0]["language"] == "fi"
    assert view["annotations"][0]["machine_generated"] is True
    assert view["annotations"][0]["review_status"] == "PROVISIONAL"
    assert view["annotations"][1]["machine_generated"] is False
    assert view["notes"][0]["id"] == "memo-1"
    assert view["temporal_series"][0]["series_id"] == "t1"


def test_dats_export_never_promotes_provisional_model_annotation() -> None:
    exported = export_dats_review(dats_review_view(_dats()))
    assert exported["annotations"][0]["provisional_ai"] is True
    assert exported["annotations"][0]["review_status"] == "PROVISIONAL"
    assert exported["annotations"][1]["provisional_ai"] is False


def test_dna_view_preserves_semantics_evidence_review_uncertainty_and_unicode() -> None:
    view = dna_graph_view(_statements(), _projection())
    assert view.projection_method == "statement affiliation"
    assert view.weighting_method == "statement count"
    assert view.temporal_scope["start"] == "2026-09-17"
    assert view.filters == {"arena": "elites"}
    assert any(node.label == "Tutkija Ω" for node in view.nodes)
    edge = next(edge for edge in view.edges if edge.id == "s2")
    assert edge.review_status == "PROVISIONAL"
    assert edge.uncertainty == "requires review"
    assert edge.evidence[0].evidence_id == "ev2"
    assert edge.evidence[0].external_ids["dna"] == "dna-8"
    assert "community/cluster != ideological formation" in view.safeguards


def test_graph_exports_are_parseable_and_keep_semantic_metadata() -> None:
    view = dna_graph_view(_statements(), _projection())
    graphml = graphml_dumps(view)
    gexf = gexf_dumps(view)
    ElementTree.fromstring(graphml)
    ElementTree.fromstring(gexf)
    assert "projection_method" in graphml
    assert "statement affiliation" in graphml
    assert "Tutkija Ω" in graphml
    assert "coded statements" in gexf

    node_csv, edge_csv = node_edge_csv(view)
    nodes = list(csv.DictReader(io.StringIO(node_csv)))
    edges = list(csv.DictReader(io.StringIO(edge_csv)))
    assert {row["node_type"] for row in nodes} == {"actor", "concept"}
    assert {row["id"] for row in edges} == {"s1", "s2"}

    payload = json.loads(graph_json(view))
    assert payload["provenance_id"] == "prov:1"
    assert payload["filters"] == {"arena": "elites"}


def test_browser_renderer_payloads_are_thin_and_renderer_neutral() -> None:
    view = dna_graph_view(_statements(), _projection())
    cytoscape = renderer_payload(view, "cytoscape")
    sigma = renderer_payload(view, "sigma")
    assert cytoscape["renderer"] == "cytoscape"
    assert cytoscape["metadata"]["node_semantics"] == view.node_semantics
    assert sigma["renderer"] == "sigma"
    assert sigma["metadata"]["projection_id"] == "p1"
    assert "x" not in sigma["nodes"][0]["attributes"]


def test_vega_lite_contract_has_safeguards_and_portable_values() -> None:
    spec = vega_lite_spec(
        [{"day": "2026-09-17", "count": 4, "formation": "ai safety"}],
        x="day",
        y="count",
        color="formation",
        title="Concept over time",
    )
    assert spec["$schema"].endswith("vega-lite/v5.json")
    assert spec["data"]["values"][0]["formation"] == "ai safety"
    assert spec["encoding"]["color"]["field"] == "formation"
    assert list(spec["usermeta"]["safeguards"]) == list(SEMANTIC_SAFEGUARDS)
