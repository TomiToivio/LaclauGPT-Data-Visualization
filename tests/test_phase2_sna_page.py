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
