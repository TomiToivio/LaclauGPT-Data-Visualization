"""Phase 2 Social Network Analysis (SNA) visualization adapter.

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


def _scalar_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        return tuple(str(item) for item in value.values() if item not in (None, ""))
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(str(item) for item in value if item not in (None, ""))
    return (str(value),)


def _metadata_values(item: Mapping[str, Any], *keys: str) -> tuple[str, ...]:
    metadata = item.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    values: list[str] = []
    for key in keys:
        values.extend(_scalar_values(item.get(key)))
        values.extend(_scalar_values(metadata.get(key)))
    return tuple(values)


def _timestamp(item: Mapping[str, Any]) -> str | None:
    values = _metadata_values(item, "timestamp", "source_timestamp", "date", "datetime")
    return values[0] if values else None


def _date_in_range(value: str | None, start: str | None, end: str | None) -> bool:
    if not value:
        return not (start or end)
    normalized = value[:10]
    if start and normalized < start:
        return False
    if end and normalized > end:
        return False
    return True


def filter_sna_product(
    product: DataProduct,
    *,
    node_types: tuple[str, ...] = (),
    platforms: tuple[str, ...] = (),
    project: str | None = None,
    dataset: str | None = None,
    start: str | None = None,
    end: str | None = None,
    discourse: tuple[str, ...] = (),
) -> DataProduct:
    """Return an upstream-semantics-preserving filtered NETWORK product.

    Filters only inspect fields already supplied by Analysis. No missing platform,
    date, discourse, project, dataset, tie, metric or community value is inferred.
    """
    capability = sna_capability(product)
    if not capability.available:
        raise ValueError(capability.reason)
    if project and (product.project or "") != project:
        payload = {**dict(product.payload), "nodes": [], "edges": []}
        return DataProduct(
            kind=product.kind,
            payload=payload,
            project=product.project,
            dataset=product.dataset,
            version=product.version,
            metadata=product.metadata,
            evidence=product.evidence,
        )
    if dataset and (product.dataset or "") != dataset:
        payload = {**dict(product.payload), "nodes": [], "edges": []}
        return DataProduct(
            kind=product.kind,
            payload=payload,
            project=product.project,
            dataset=product.dataset,
            version=product.version,
            metadata=product.metadata,
            evidence=product.evidence,
        )

    wanted_types = {value for value in node_types if value}
    wanted_platforms = {value for value in platforms if value}
    wanted_discourse = {value for value in discourse if value}
    raw_nodes = [node for node in product.payload["nodes"] if isinstance(node, Mapping)]
    raw_edges = [edge for edge in product.payload["edges"] if isinstance(edge, Mapping)]

    allowed_nodes: set[str] = set()
    for node in raw_nodes:
        node_id = _node_id(node)
        if not node_id:
            continue
        if wanted_types and _node_type(node) not in wanted_types:
            continue
        node_platforms = set(_metadata_values(node, "platform", "source_platform"))
        if wanted_platforms and node_platforms and node_platforms.isdisjoint(wanted_platforms):
            continue
        node_discourse = set(
            _metadata_values(
                node,
                "concept",
                "concepts",
                "discourse_concept",
                "formation",
                "formations",
            )
        )
        if wanted_discourse and node_discourse and node_discourse.isdisjoint(wanted_discourse):
            continue
        if (start or end) and not _date_in_range(_timestamp(node), start, end):
            continue
        allowed_nodes.add(node_id)

    kept_edges: list[dict[str, Any]] = []
    for edge in raw_edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if source not in allowed_nodes or target not in allowed_nodes:
            continue
        edge_platforms = set(_metadata_values(edge, "platform", "source_platform"))
        if wanted_platforms and (
            not edge_platforms or edge_platforms.isdisjoint(wanted_platforms)
        ):
            continue
        edge_discourse = set(
            _metadata_values(
                edge,
                "concept",
                "concepts",
                "discourse_concept",
                "formation",
                "formations",
            )
        )
        if wanted_discourse and (
            not edge_discourse or edge_discourse.isdisjoint(wanted_discourse)
        ):
            continue
        if (start or end) and not _date_in_range(_timestamp(edge), start, end):
            continue
        kept_edges.append(dict(edge))

    connected = {
        str(endpoint)
        for edge in kept_edges
        for endpoint in (edge.get("source"), edge.get("target"))
        if endpoint
    }
    if raw_edges and (wanted_platforms or wanted_discourse or start or end):
        allowed_nodes &= connected

    payload = dict(product.payload)
    payload["nodes"] = [
        dict(node) for node in raw_nodes if _node_id(node) in allowed_nodes
    ]
    payload["edges"] = kept_edges
    derived_results = payload.get("derived_results")
    if isinstance(derived_results, list):
        payload["derived_results"] = [
            dict(result)
            for result in derived_results
            if isinstance(result, Mapping)
            and str(result.get("target_id") or "") in allowed_nodes
        ]
    return DataProduct(
        kind=product.kind,
        payload=payload,
        project=product.project,
        dataset=product.dataset,
        version=product.version,
        metadata=product.metadata,
        evidence=product.evidence,
    )


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
            "phase": 2,
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
