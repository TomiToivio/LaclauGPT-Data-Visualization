"""Pure researcher-facing operations over the backend-neutral graph contract."""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from .graph_api import GraphEnvelope, evidence_refs


def _timestamp(item: Mapping[str, Any]) -> datetime | None:
    raw = item.get("timestamp") or (item.get("properties") or {}).get("timestamp")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def filter_graph(
    graph: GraphEnvelope,
    *,
    node_types: Iterable[str] = (),
    edge_types: Iterable[str] = (),
    layers: Iterable[str] = (),
    start: str | None = None,
    end: str | None = None,
) -> GraphEnvelope:
    """Apply view-only filters without inventing analytical semantics."""
    wanted_nodes = set(node_types)
    wanted_edges = set(edge_types)
    wanted_layers = set(layers)
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")) if start else None
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None

    def in_time(item: Mapping[str, Any]) -> bool:
        ts = _timestamp(item)
        if ts is None:
            return True
        return not ((start_dt and ts < start_dt) or (end_dt and ts > end_dt))

    nodes = [
        node for node in graph.nodes
        if (not wanted_nodes or str(node.get("type")) in wanted_nodes)
        and (not wanted_layers or str(node.get("layer", "source")) in wanted_layers)
        and in_time(node)
    ]
    node_ids = {str(node.get("id")) for node in nodes}
    edges = [
        edge for edge in graph.edges
        if str(edge.get("source")) in node_ids
        and str(edge.get("target")) in node_ids
        and (not wanted_edges or str(edge.get("type")) in wanted_edges)
        and (not wanted_layers or str(edge.get("layer", "source")) in wanted_layers)
        and in_time(edge)
    ]
    return GraphEnvelope(
        nodes=tuple(nodes),
        edges=tuple(edges),
        continuation=graph.continuation,
        truncated=graph.truncated,
        metadata={**dict(graph.metadata), "view_filtered": True},
        provenance=graph.provenance,
    )


def ego_graph(graph: GraphEnvelope, roots: Iterable[str], *, hops: int = 1) -> GraphEnvelope:
    """Return a bounded k-hop view from already bounded graph data."""
    hops = max(0, min(int(hops), 4))
    adjacency: dict[str, set[str]] = {}
    for edge in graph.edges:
        source, target = str(edge.get("source")), str(edge.get("target"))
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)
    seen = {str(root) for root in roots}
    queue = deque((root, 0) for root in seen)
    while queue:
        node, depth = queue.popleft()
        if depth >= hops:
            continue
        for neighbour in adjacency.get(node, ()):
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append((neighbour, depth + 1))
    nodes = tuple(node for node in graph.nodes if str(node.get("id")) in seen)
    edges = tuple(
        edge for edge in graph.edges
        if str(edge.get("source")) in seen and str(edge.get("target")) in seen
    )
    return GraphEnvelope(
        nodes=nodes,
        edges=edges,
        truncated=graph.truncated,
        metadata={**dict(graph.metadata), "ego_roots": sorted(seen & {str(r) for r in roots}), "hops": hops},
        provenance=graph.provenance,
    )


def compare_graphs(left: GraphEnvelope, right: GraphEnvelope) -> dict[str, Any]:
    """Compare two time slices without assigning theoretical meaning to change."""
    left_nodes = {str(node.get("id")) for node in left.nodes}
    right_nodes = {str(node.get("id")) for node in right.nodes}
    left_edges = {(str(e.get("source")), str(e.get("type")), str(e.get("target"))) for e in left.edges}
    right_edges = {(str(e.get("source")), str(e.get("type")), str(e.get("target"))) for e in right.edges}
    return {
        "nodes_added": sorted(right_nodes - left_nodes),
        "nodes_removed": sorted(left_nodes - right_nodes),
        "edges_added": sorted(right_edges - left_edges),
        "edges_removed": sorted(left_edges - right_edges),
        "left": {"nodes": len(left_nodes), "edges": len(left_edges)},
        "right": {"nodes": len(right_nodes), "edges": len(right_edges)},
        "interpretation": "descriptive graph delta; no theoretical status is inferred",
    }


def provenance_inspector(item: Mapping[str, Any]) -> dict[str, Any]:
    """Compact evidence path for node/edge drill-down."""
    properties = item.get("properties") or {}
    return {
        "id": item.get("id"),
        "type": item.get("type"),
        "source_url": item.get("source_url") or properties.get("source_url"),
        "evidence_refs": list(evidence_refs(item)),
        "analysis_run": item.get("analysis_run") or properties.get("analysis_run"),
        "review_status": item.get("review_status") or item.get("validation_status"),
        "properties": dict(properties),
    }
