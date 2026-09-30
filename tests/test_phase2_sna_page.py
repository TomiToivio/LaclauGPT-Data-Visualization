from __future__ import annotations

import pytest

from laclaugpt_visualization.products import ProductKind
from laclaugpt_visualization.sna import filter_sna_product, sna_capability, sna_envelope
from laclaugpt_visualization.sna_page import network_product_from_mapping


def _network():
    return {
        "kind": "network",
        "project": "ai26",
        "version": "2",
        "metadata": {
            "exports": {
                "graphml": "analysis://ai26/network.graphml",
                "gexf": "analysis://ai26/network.gexf",
                "rdf": "analysis://ai26/research.ttl",
            }
        },
        "payload": {
            "nodes": [
                {"id": "human:1", "label": "Researcher", "type": "person"},
                {"id": "agent:1", "label": "Agent", "type": "ai_agent"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "human:1",
                    "target": "agent:1",
                    "type": "communicates_with",
                    "directed": True,
                    "weight": 2,
                    "source_url": "https://example.org/source/1",
                    "evidence_ids": ["ev:1"],
                }
            ],
            "measures": {
                "degree": {"human:1": 1, "agent:1": 1},
                "betweenness": {"human:1": 0.0, "agent:1": 0.0},
            },
        },
    }


def test_phase2_network_product_preserves_analysis_contract():
    product = network_product_from_mapping(_network())
    assert product.kind is ProductKind.NETWORK
    assert product.project == "ai26"
    assert product.version == "2"
    assert product.metadata["exports"]["graphml"].endswith(".graphml")
    assert sna_capability(product).available is True

    graph = sna_envelope(product)
    assert {node["type"] for node in graph.nodes} == {"person", "ai_agent"}
    assert graph.edges[0]["provenance_refs"] == ["ev:1"]
    assert graph.edges[0]["properties"]["source_url"] == "https://example.org/source/1"


def test_phase2_rejects_non_network_products():
    data = _network()
    data["kind"] = "knowledge_graph"
    with pytest.raises(ValueError, match="NETWORK"):
        network_product_from_mapping(data)


def test_phase2_rejects_missing_nodes_or_edges():
    data = _network()
    del data["payload"]["edges"]
    with pytest.raises(ValueError, match="nodes and edges"):
        network_product_from_mapping(data)



def test_phase2_filters_use_only_upstream_metadata():
    data = _network()
    data["dataset"] = "pilot"
    data["payload"]["nodes"][0]["metadata"] = {
        "platform": "x",
        "formation": "accelerationist",
        "timestamp": "2026-09-20T12:00:00Z",
    }
    data["payload"]["nodes"][1]["metadata"] = {
        "platform": "x",
        "formation": "accelerationist",
        "timestamp": "2026-09-20T12:00:00Z",
    }
    data["payload"]["edges"][0]["platform"] = "x"
    data["payload"]["edges"][0]["formation"] = "accelerationist"
    data["payload"]["edges"][0]["timestamp"] = "2026-09-20T12:00:00Z"

    product = network_product_from_mapping(data)
    filtered = filter_sna_product(
        product,
        node_types=("person", "ai_agent"),
        platforms=("x",),
        project="ai26",
        dataset="pilot",
        start="2026-09-01",
        end="2026-09-30",
        discourse=("accelerationist",),
    )
    assert len(filtered.payload["nodes"]) == 2
    assert len(filtered.payload["edges"]) == 1

    empty = filter_sna_product(product, platforms=("tiktok",))
    assert empty.payload["nodes"] == []
    assert empty.payload["edges"] == []


def _analytical_graph():
    return {
        "schema_version": "1.0.0",
        "project_id": "AI26",
        "base_uri": "https://data.example/laclaugpt",
        "metadata": {"projection": "cross-layer", "exports": {"rdf": "analysis://AI26/research.ttl"}},
        "nodes": [
            {
                "id": "actor:a",
                "uri": "https://data.example/laclaugpt/AI26/actor/a",
                "kind": "actor",
                "layer": "sna",
                "label": "Actor A",
                "assertion_kind": "empirical",
                "properties": {},
                "provenance": {
                    "source_id": "source:1",
                    "source_url": "https://example.org/source/1",
                    "evidence_ids": ["ev:1"],
                },
            },
            {
                "id": "actor:b",
                "uri": "https://data.example/laclaugpt/AI26/actor/b",
                "kind": "actor",
                "layer": "sna",
                "label": "Actor B",
                "assertion_kind": "empirical",
                "properties": {},
                "provenance": {
                    "source_id": "source:1",
                    "source_url": "https://example.org/source/1",
                    "evidence_ids": [],
                },
            },
            {
                "id": "derived:degree-a",
                "uri": "https://data.example/laclaugpt/AI26/sna-result/degree-a",
                "kind": "derived-centrality",
                "layer": "sna",
                "assertion_kind": "graph-statistical",
                "properties": {"value": 0.5, "parameters": {"name": "degree"}},
                "provenance": {"source_id": "derived:sna", "method": "networkx"},
                "snapshot_id": "snapshot-1",
            },
        ],
        "edges": [
            {
                "id": "rel:1",
                "uri": "https://data.example/laclaugpt/AI26/edge/sna/rel:1",
                "source": "actor:a",
                "target": "actor:b",
                "kind": "mention",
                "layer": "sna",
                "directed": True,
                "weight": 1.0,
                "assertion_kind": "empirical",
                "properties": {"platform": "x"},
                "provenance": {
                    "source_id": "source:1",
                    "source_url": "https://example.org/source/1",
                    "evidence_ids": ["ev:1"],
                },
                "valid_from": "2026-09-20T12:00:00Z",
            },
            {
                "id": "degree-a:describes",
                "uri": "https://data.example/laclaugpt/AI26/edge/sna-derived/degree-a",
                "source": "derived:degree-a",
                "target": "actor:a",
                "kind": "describes",
                "layer": "sna",
                "directed": True,
                "assertion_kind": "graph-statistical",
                "properties": {"metric": "centrality", "source_relation_ids": ["rel:1"]},
                "provenance": {"source_id": "derived:sna", "method": "networkx"},
                "snapshot_id": "snapshot-1",
            },
        ],
    }


def test_phase2_accepts_canonical_analysis_analytical_graph():
    product = network_product_from_mapping(_analytical_graph())

    assert product.kind is ProductKind.NETWORK
    assert product.project == "AI26"
    assert product.version == "1.0.0"
    assert product.metadata["source_contract"] == "AnalyticalGraph"
    assert product.metadata["exports"]["rdf"].endswith(".ttl")
    assert {node["id"] for node in product.payload["nodes"]} == {"actor:a", "actor:b"}
    assert len(product.payload["edges"]) == 1
    assert product.payload["edges"][0]["type"] == "mention"
    assert product.payload["edges"][0]["evidence_ids"] == ["ev:1"]
    assert product.payload["derived_results"][0]["metric"] == "centrality"
    assert product.payload["derived_results"][0]["value"] == 0.5

    graph = sna_envelope(product)
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert graph.edges[0]["properties"]["platform"] == "x"


def test_phase2_rejects_analytical_graph_without_sna_layer():
    data = _analytical_graph()
    for node in data["nodes"]:
        node["layer"] = "dna"
    for edge in data["edges"]:
        edge["layer"] = "dna"

    with pytest.raises(ValueError, match="NETWORK|AnalyticalGraph"):
        network_product_from_mapping(data)


def test_phase2_analytical_graph_filters_derived_results_with_visible_nodes():
    product = network_product_from_mapping(_analytical_graph())

    kept = filter_sna_product(product, platforms=("x",))
    assert {node["id"] for node in kept.payload["nodes"]} == {"actor:a", "actor:b"}
    assert len(kept.payload["derived_results"]) == 1

    hidden = filter_sna_product(product, platforms=("tiktok",))
    assert hidden.payload["nodes"] == []
    assert hidden.payload["edges"] == []
    assert hidden.payload["derived_results"] == []
