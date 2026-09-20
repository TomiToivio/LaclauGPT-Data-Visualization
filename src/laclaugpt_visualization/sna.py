"""Isolated Phase-1 Social Network Analysis (SNA) visualization adapter.

Visualization consumes an explicit upstream NETWORK product. It never derives social
ties, communities, or centrality from canonical records.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .graph_api import GraphEnvelope
from .products import DataProduct, ProductKind


SNA_CAVEAT = (
    "Network degree, centrality, PageRank, clustering, component membership and layout "
    "are descriptive structural measures. They do not by themselves establish influence, "
    "power, hegemony, ideology, coordination, brokerage, or theoretical significance."
)


@dataclass(frozen=True, slots=True)
class SNACapability:
    available: bool
    reason: str


def sna_capability(product: DataProduct | None) -> SNACapability:
    """Return whether a stable explicit upstream SNA/network product is renderable."""
    if product is None:
        return SNACapability(False, "No upstream NETWORK product is available.")
    if product.kind != ProductKind.NETWORK:
        return SNACapability(False, "SNA requires an explicit NETWORK product from Analysis.")
    if not isinstance(product.payload, Mapping):
        return SNACapability(False, "NETWORK payload must be a mapping with nodes and edges.")
    nodes = product.payload.get("nodes")
    edges = product.payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return SNACapability(False, "NETWORK payload must contain list-valued nodes and edges.")
    return SNACapability(True, "Explicit upstream NETWORK product is available.")


def _node_id(node: Mapping[str, Any]) -> str:
    return str(node.get("node_id") or node.get("id") or "").strip()


def _node_type(node: Mapping[str, Any]) -> str:
    return str(node.get("node_type") or node.get("type") or "actor").strip() or "actor"


def _measure_for(
    measures: Mapping[str, Any], measure: str, node_id: str
) -> int | float | None:
    values = measures.get(measure)
    if not isinstance(values, Mapping) or node_id not in values:
        return None
    value = values[node_id]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def sna_envelope(
    product: DataProduct,
    *,
    max_nodes: int = 250,
    max_edges: int = 500,
) -> GraphEnvelope:
    """Adapt a precomputed Analysis NETWORK product to the shared graph envelope.

    No social edges or network measures are computed here. Bounding uses upstream
    degree only when supplied; otherwise stable input order is retained.
    """
    capability = sna_capability(product)
    if not capability.available:
        raise ValueError(capability.reason)

    payload = product.payload
    raw_nodes = [node for node in payload["nodes"] if isinstance(node, Mapping)]
    raw_edges = [edge for edge in payload["edges"] if isinstance(edge, Mapping)]
    measures = payload.get("measures")
    if not isinstance(measures, Mapping):
        measures = {}

    node_limit = max(1, int(max_nodes))
    edge_limit = max(1, int(max_edges))

    indexed_nodes: list[tuple[int, Mapping[str, Any], str]] = []
    for index, node in enumerate(raw_nodes):
        node_id = _node_id(node)
        if node_id:
            indexed_nodes.append((index, node, node_id))

    def sort_key(item: tuple[int, Mapping[str, Any], str]) -> tuple[float, int]:
        index, _node, node_id = item
        degree = _measure_for(measures, "degree", node_id)
        return (-(float(degree) if degree is not None else -1.0), index)

    if isinstance(measures.get("degree"), Mapping):
        indexed_nodes = sorted(indexed_nodes, key=sort_key)
    selected = indexed_nodes[:node_limit]
    selected_ids = {node_id for _index, _node, node_id in selected}

    nodes: list[dict[str, Any]] = []
    for _index, node, node_id in selected:
        metadata = node.get("metadata")
        if not isinstance(metadata, Mapping):
            metadata = {}
        source_urls = metadata.get("source_urls") or ()
        if isinstance(source_urls, str):
            source_urls = (source_urls,)
        evidence_ids = metadata.get("evidence_ids") or ()
        if isinstance(evidence_ids, str):
            evidence_ids = (evidence_ids,)

        properties: dict[str, Any] = {
            "full_id": node_id,
            "upstream_metadata": dict(metadata),
        }
        for measure in (
            "degree",
            "in_degree",
            "out_degree",
            "betweenness",
            "pagerank",
            "clustering",
            "k_core",
        ):
            value = _measure_for(measures, measure, node_id)
            if value is not None:
                properties[measure] = value

        nodes.append(
            {
                "id": node_id,
                "label": str(node.get("label") or node_id),
                "type": _node_type(node),
                "layer": "sna",
                "properties": properties,
                "provenance_refs": [str(ref) for ref in evidence_ids if str(ref)],
                "source_urls": [str(url) for url in source_urls if str(url)],
            }
        )

    edges: list[dict[str, Any]] = []
    for index, edge in enumerate(raw_edges):
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if not source or not target or source not in selected_ids or target not in selected_ids:
            continue
        evidence_ids = edge.get("evidence_ids") or edge.get("evidence_refs") or ()
        if isinstance(evidence_ids, str):
            evidence_ids = (evidence_ids,)
        source_url = str(edge.get("source_url") or "").strip()
        metadata = edge.get("metadata")
        if not isinstance(metadata, Mapping):
            metadata = {}
        edges.append(
            {
                "id": str(edge.get("id") or f"sna:{index}"),
                "source": source,
                "target": target,
                "type": str(
                    edge.get("relation_type") or edge.get("type") or "related_to"
                ),
                "layer": "sna",
                "directed": bool(edge.get("directed", True)),
                "weight": float(edge.get("weight") or 1.0),
                "properties": {
                    "observed": bool(edge.get("observed", True)),
                    "timestamp": edge.get("timestamp"),
                    "platform": edge.get("platform"),
                    "collection_id": edge.get("collection_id"),
                    "source_url": source_url or None,
                    "upstream_metadata": dict(metadata),
                },
                "provenance_refs": [str(ref) for ref in evidence_ids if str(ref)],
            }
        )
        if len(edges) >= edge_limit:
            break

    return GraphEnvelope(
        nodes=tuple(nodes),
        edges=tuple(edges),
        truncated=len(indexed_nodes) > node_limit or len(raw_edges) > len(edges),
        metadata={
            "contract": "laclaugpt.graph.v1",
            "adapter": "sna-network-product",
            "phase": 1,
            "source_product_kind": product.kind.value,
            "source_product_version": product.version,
            "descriptive_only": True,
            "caveat": SNA_CAVEAT,
            **dict(product.metadata),
        },
        provenance={
            "evidence_refs": [
                {
                    "record_id": ref.record_id,
                    "source_url": ref.source_url,
                    "artifact_id": ref.artifact_id,
                    "selector": dict(ref.selector),
                }
                for ref in product.evidence
            ]
        },
    )
