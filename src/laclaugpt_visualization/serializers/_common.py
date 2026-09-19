"""Shared validation for optional graph serializers."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

INTERPRETATION_WARNING = (
    "Descriptive network view only: degree is not a nodal point, layout proximity is not "
    "equivalence, clusters are not ideologies, and frequency is not hegemony."
)


def normalize_projection(projection: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return defensive copies of nodes/edges from a graph_projection-like mapping."""
    nodes = projection.get("nodes", [])
    edges = projection.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise TypeError("projection nodes and edges must be lists")

    clean_nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, Mapping):
            raise TypeError("every node must be a mapping")
        value = dict(node)
        node_id = str(value.get("id") or "").strip()
        if not node_id:
            raise ValueError("every node requires a non-empty id")
        if node_id in node_ids:
            raise ValueError(f"duplicate node id: {node_id}")
        node_ids.add(node_id)
        value["id"] = node_id
        clean_nodes.append(value)

    clean_edges: list[dict[str, Any]] = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, Mapping):
            raise TypeError("every edge must be a mapping")
        value = dict(edge)
        source = str(value.get("source") or "").strip()
        target = str(value.get("target") or "").strip()
        if not source or not target:
            raise ValueError("every edge requires source and target")
        value["source"] = source
        value["target"] = target
        value.setdefault("id", f"e{index}:{source}->{target}")
        clean_edges.append(value)
    return clean_nodes, clean_edges
