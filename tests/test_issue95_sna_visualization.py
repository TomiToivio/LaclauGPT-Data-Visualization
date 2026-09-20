from __future__ import annotations

import pytest

from laclaugpt_visualization.products import DataProduct, EvidenceRef, ProductKind
from laclaugpt_visualization.sna import SNA_CAVEAT, sna_capability, sna_envelope


def _product() -> DataProduct:
    return DataProduct(
        kind=ProductKind.NETWORK,
        version="1",
        metadata={"producer": "laclaugpt-data-analysis"},
        payload={
            "nodes": [
                {"node_id": "actor:a", "node_type": "actor", "label": "Actor A"},
                {"node_id": "actor:b", "node_type": "actor", "label": "Actor B"},
                {"node_id": "actor:c", "node_type": "actor", "label": "Actor C"},
            ],
            "edges": [
                {
                    "source": "actor:a",
                    "target": "actor:b",
                    "relation_type": "mentions",
                    "observed": True,
                    "weight": 2,
                    "source_url": "https://example.invalid/post/1",
                    "evidence_ids": ["ev:1"],
                },
                {
                    "source": "actor:b",
                    "target": "actor:c",
                    "relation_type": "replies_to",
                    "observed": True,
                    "weight": 1,
                    "source_url": "https://example.invalid/post/2",
                    "evidence_ids": ["ev:2"],
                },
            ],
            "measures": {
                "degree": {"actor:a": 1, "actor:b": 2, "actor:c": 1},
                "betweenness": {"actor:a": 0.0, "actor:b": 1.0, "actor:c": 0.0},
                "pagerank": {"actor:a": 0.2, "actor:b": 0.5, "actor:c": 0.3},
            },
        },
        evidence=(
            EvidenceRef(
                record_id="record:1",
                source_url="https://example.invalid/post/1",
                selector={"evidence_id": "ev:1"},
            ),
        ),
    )


def test_sna_requires_explicit_upstream_network_product() -> None:
    assert not sna_capability(None).available
    wrong = DataProduct(kind=ProductKind.RECORDS, payload=[])
    assert not sna_capability(wrong).available
    malformed = DataProduct(kind=ProductKind.NETWORK, payload={"nodes": []})
    assert not sna_capability(malformed).available
    with pytest.raises(ValueError, match="nodes and edges"):
        sna_envelope(malformed)


def test_sna_preserves_edge_source_and_evidence_traceability() -> None:
    graph = sna_envelope(_product())
    edge = graph.edges[0]
    assert edge["properties"]["source_url"] == "https://example.invalid/post/1"
    assert edge["provenance_refs"] == ["ev:1"]
    assert graph.provenance["evidence_refs"][0]["source_url"] == "https://example.invalid/post/1"


def test_sna_uses_upstream_measures_without_recomputing_them() -> None:
    graph = sna_envelope(_product())
    by_id = {node["id"]: node for node in graph.nodes}
    assert by_id["actor:b"]["properties"]["degree"] == 2
    assert by_id["actor:b"]["properties"]["betweenness"] == 1.0
    assert by_id["actor:b"]["properties"]["pagerank"] == 0.5
    assert "centrality" in SNA_CAVEAT
    assert graph.metadata["descriptive_only"] is True


def test_sna_rendering_is_bounded_and_does_not_infer_missing_edges() -> None:
    graph = sna_envelope(_product(), max_nodes=2, max_edges=1)
    assert len(graph.nodes) == 2
    assert len(graph.edges) <= 1
    assert graph.truncated is True
    assert {node["id"] for node in graph.nodes} == {"actor:a", "actor:b"}
    assert graph.edges[0]["source"] == "actor:a"
    assert graph.edges[0]["target"] == "actor:b"


def test_sna_missing_measures_preserves_input_order_instead_of_computing_degree() -> None:
    product = _product()
    product.payload["measures"] = {}
    graph = sna_envelope(product, max_nodes=2)
    assert [node["id"] for node in graph.nodes] == ["actor:a", "actor:b"]
    assert all("degree" not in node["properties"] for node in graph.nodes)
