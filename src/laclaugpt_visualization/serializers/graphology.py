"""Serialize a derived graph projection for Graphology/Sigma.js."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._common import INTERPRETATION_WARNING, normalize_projection


def to_graphology(projection: Mapping[str, Any]) -> dict[str, Any]:
    """Return Graphology import-friendly JSON without adding analytical inference."""
    nodes, edges = normalize_projection(projection)
    graph_nodes = []
    for node in nodes:
        attributes = dict(node)
        key = attributes.pop("id")
        graph_nodes.append({"key": key, "attributes": attributes})

    graph_edges = []
    for edge in edges:
        attributes = dict(edge)
        key = str(attributes.pop("id"))
        source = str(attributes.pop("source"))
        target = str(attributes.pop("target"))
        graph_edges.append(
            {"key": key, "source": source, "target": target, "attributes": attributes}
        )

    return {
        "schema": "laclaugpt.graphology.v1",
        "options": {"type": "mixed", "multi": True, "allowSelfLoops": True},
        "attributes": {
            "descriptive_only": True,
            "interpretation_warning": INTERPRETATION_WARNING,
            "bounded": bool(projection.get("bounded", False)),
            "truncated": bool(projection.get("truncated", False)),
        },
        "nodes": graph_nodes,
        "edges": graph_edges,
    }
