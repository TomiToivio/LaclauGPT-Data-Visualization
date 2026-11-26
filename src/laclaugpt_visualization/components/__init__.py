"""Streamlit bridge for the vendored D3 force-directed multilayer graph (#330).

The component is a custom frontend rather than a Plotly scatter because the issue asks for a
genuinely interactive graph: drag-to-pin, zoom and pan, hover detail, click-to-inspect, layer
toggles and search. Plotly can animate a fixed layout but cannot do those things without fighting
the library.

Everything here is pure data shaping plus one ``declare_component`` call, so the payload building is
testable without a browser. The frontend never receives a MongoDB handle, a path or a credential:
it receives nodes, edges and the disclosure that says whether the view is bounded.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

from laclaugpt_visualization.multilayer import MultilayerGraph, to_envelope

_COMPONENT = components.declare_component(
    "ai26_multilayer_graph",
    path=str(Path(__file__).resolve().parent / "multilayer_graph"),
)

LAYER_COLORS = {"da": "#ff4d6d", "dna": "#35d0ba", "sna": "#ffc857", "other": "#8f9bb3"}


def payload_from_multilayer(result: MultilayerGraph, *, max_nodes: int = 400) -> dict[str, Any]:
    """Shape a built graph for the component, bounded and self-describing."""
    envelope = to_envelope(result)
    nodes = []
    for node in envelope.nodes[:max_nodes]:
        degree = result.graph.degree(str(node["id"]))
        layers = list(node.get("layers") or ())
        nodes.append(
            {
                "id": str(node["id"]),
                "label": str(node.get("label") or node["id"]),
                "type": str(node.get("type") or ""),
                "layer": layers[0] if len(layers) == 1 else "bridge" if len(layers) > 1 else "other",
                "layers": layers,
                "degree": int(degree),
                "raw_ids": dict((node.get("properties") or {}).get("raw_ids") or {}),
            }
        )
    keep = {node["id"] for node in nodes}
    edges = [
        {
            "id": str(edge["id"]),
            "source": str(edge["source"]),
            "target": str(edge["target"]),
            "type": str(edge.get("type") or "related"),
            "layer": str(edge.get("layer") or "other"),
            "cross_layer": bool(edge.get("cross_layer")),
            "directed": bool(edge.get("directed", True)),
            "weight": float(edge.get("weight") or 1.0),
        }
        for edge in envelope.edges
        if str(edge["source"]) in keep and str(edge["target"]) in keep
    ]
    disclosure = dict(envelope.metadata.get("disclosure") or {})
    if len(envelope.nodes) > len(nodes):
        disclosure["truncated"] = True
        disclosure["dropped_nodes"] = int(disclosure.get("dropped_nodes") or 0) + (
            len(envelope.nodes) - len(nodes)
        )
    return {"nodes": nodes, "edges": edges, "disclosure": disclosure}


def payload_from_projection(
    projection: Mapping[str, Any],
    *,
    max_nodes: int = 400,
) -> dict[str, Any]:
    """Shape the dashboard's existing canonical projection for the same component.

    The projection has no discourse layers, so every node is ``other``. It is shown as a network of
    records and relations, never labelled as DA/DNA/SNA evidence.
    """
    raw_nodes: Sequence[Mapping[str, Any]] = projection.get("nodes") or ()  # type: ignore[assignment]
    raw_edges: Sequence[Mapping[str, Any]] = projection.get("edges") or ()  # type: ignore[assignment]
    nodes = []
    for node in raw_nodes[:max_nodes]:
        node_id = str(node.get("id") or node.get("source_url") or "")
        if not node_id:
            continue
        nodes.append(
            {
                "id": node_id,
                "label": str(node.get("label") or node.get("name") or node_id),
                "type": str(node.get("type") or "record"),
                "layer": "other",
                "layers": ["other"],
                "degree": int(node.get("degree") or 0),
                "raw_ids": {},
            }
        )
    keep = {node["id"] for node in nodes}
    edges = [
        {
            "id": str(edge.get("id") or f"{edge.get('source')}->{edge.get('target')}:{index}"),
            "source": str(edge.get("source") or ""),
            "target": str(edge.get("target") or ""),
            "type": str(edge.get("type") or "related"),
            "layer": "other",
            "cross_layer": False,
            "directed": bool(edge.get("directed", True)),
            "weight": float(edge.get("weight") or 1.0),
        }
        for index, edge in enumerate(raw_edges)
        if str(edge.get("source")) in keep and str(edge.get("target")) in keep
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "disclosure": {
            "truncated": bool(projection.get("truncated")),
            "nodes": len(nodes),
            "edges": len(edges),
            "layer_counts": {"other": len(nodes)} if nodes else {},
        },
    }


def render_graph(payload: Mapping[str, Any], *, key: str = "ai26_multilayer_graph", height: int = 680):
    """Draw the component and return the last inspected node, if the researcher clicked one."""
    return _COMPONENT(
        nodes=list(payload.get("nodes") or ()),
        edges=list(payload.get("edges") or ()),
        disclosure=dict(payload.get("disclosure") or {}),
        key=key,
        default=None,
        height=height,
    )
