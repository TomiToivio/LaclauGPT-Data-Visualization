"""Phase-1 researcher-facing graph explorer for backend-neutral graph payloads."""
from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from typing import Any

import plotly.graph_objects as go

from .graph_api import GraphEnvelope, jsonld_subgraph
from .rdf import compact_uri
from .transforms import graph_projection, temporal_graph_projection

_SOURCE_EDGE_TYPES = {
    "reply", "replies_to", "mention", "mentions", "repost", "reposts",
    "quote", "quotes", "link", "links_to", "authored_by", "published_by",
}


def _node_type(node: Mapping[str, Any]) -> str:
    kinds = node.get("kinds") or ()
    if isinstance(kinds, str):
        return kinds
    return str(kinds[0]) if kinds else str(node.get("type") or "resource")


def _edge_layer(edge: Mapping[str, Any]) -> str:
    edge_type = str(edge.get("type") or "related_to").casefold()
    return "source" if edge_type in _SOURCE_EDGE_TYPES else "laclau"


def projection_envelope(
    frame,
    *,
    max_nodes: int = 250,
    max_edges: int = 500,
    clock: str | None = None,
    start: object = None,
    end: object = None,
) -> GraphEnvelope:
    """Convert the bounded canonical projection into the shared graph contract.

    Supplying a clock enables Phase-1 temporal slicing over exactly one canonical clock.
    """
    if clock is None:
        projected = graph_projection(frame, max_nodes=max_nodes, max_edges=max_edges)
    else:
        projected = temporal_graph_projection(
            frame,
            clock=clock,
            start=start,
            end=end,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )
    nodes = []
    for raw in projected["nodes"]:
        node = dict(raw)
        node_type = _node_type(node)
        nodes.append(
            {
                "id": str(node["id"]),
                "label": compact_uri(str(node.get("label") or node["id"])),
                "type": node_type,
                "layer": "laclau" if node_type in {"signifier", "formation", "topic"} else "source",
                "properties": {
                    "degree": int(node.get("degree") or 0),
                    "kinds": list(node.get("kinds") or ()),
                    "full_id": str(node["id"]),
                },
                "provenance_refs": [],
            }
        )

    edges = []
    for index, raw in enumerate(projected["edges"]):
        edge = dict(raw)
        edges.append(
            {
                "id": str(edge.get("id") or f"projection:{index}"),
                "source": str(edge["source"]),
                "target": str(edge["target"]),
                "type": str(edge.get("type") or "related_to"),
                "layer": _edge_layer(edge),
                "directed": True,
                "weight": float(edge.get("weight") or 1.0),
                "properties": {
                    "edge_status": edge.get("edge_status"),
                    "record_count": int(edge.get("record_count") or 1),
                    "source_urls": list(edge.get("source_urls") or ()),
                },
                "provenance_refs": list(edge.get("evidence_refs") or ()),
            }
        )

    return GraphEnvelope(
        nodes=tuple(nodes),
        edges=tuple(edges),
        truncated=bool(projected.get("truncated")),
        metadata={
            "contract": "laclaugpt.graph.v1",
            "backend": "canonical-frame",
            "phase": 1,
            "layers": ["source", "provenance", "laclau"],
            **({"temporal": projected["temporal"]} if "temporal" in projected else {}),
        },
    )


def filter_explorer_graph(
    graph: GraphEnvelope,
    *,
    query: str = "",
    node_types: Iterable[str] = (),
    edge_types: Iterable[str] = (),
    layers: Iterable[str] = (),
    min_weight: float = 0.0,
) -> GraphEnvelope:
    """Filter a bounded graph while preserving only edges whose endpoints remain visible."""
    wanted_node_types = set(node_types)
    wanted_edge_types = set(edge_types)
    wanted_layers = set(layers)
    needle = query.strip().casefold()

    nodes = []
    for node in graph.nodes:
        label = str(node.get("label") or node.get("id") or "")
        full_id = str((node.get("properties") or {}).get("full_id") or node.get("id") or "")
        if wanted_node_types and str(node.get("type")) not in wanted_node_types:
            continue
        if wanted_layers and str(node.get("layer")) not in wanted_layers:
            continue
        if needle and needle not in label.casefold() and needle not in full_id.casefold():
            continue
        nodes.append(node)

    node_ids = {str(node.get("id")) for node in nodes}
    edges = [
        edge
        for edge in graph.edges
        if str(edge.get("source")) in node_ids
        and str(edge.get("target")) in node_ids
        and (not wanted_edge_types or str(edge.get("type")) in wanted_edge_types)
        and (not wanted_layers or str(edge.get("layer")) in wanted_layers)
        and float(edge.get("weight") or 0.0) >= min_weight
    ]
    return GraphEnvelope(
        nodes=tuple(nodes),
        edges=tuple(edges),
        truncated=graph.truncated,
        metadata={**dict(graph.metadata), "filtered": True},
        provenance=graph.provenance,
    )


def evidence_for_edge(edge: Mapping[str, Any]) -> dict[str, Any]:
    properties = dict(edge.get("properties") or {})
    return {
        "edge_id": edge.get("id"),
        "relation": edge.get("type"),
        "source": edge.get("source"),
        "target": edge.get("target"),
        "weight": edge.get("weight"),
        "status": properties.get("edge_status"),
        "record_count": properties.get("record_count"),
        "source_urls": list(properties.get("source_urls") or ()),
        "evidence_refs": list(edge.get("provenance_refs") or ()),
    }


def _positions(graph: GraphEnvelope) -> dict[str, tuple[float, float]]:
    """Deterministic bounded layout; layout distance carries no analytical meaning."""
    ordered = sorted(
        graph.nodes,
        key=lambda node: (-int((node.get("properties") or {}).get("degree") or 0), str(node.get("id"))),
    )
    total = max(1, len(ordered))
    return {
        str(node["id"]): (
            math.cos((2 * math.pi * index) / total),
            math.sin((2 * math.pi * index) / total),
        )
        for index, node in enumerate(ordered)
    }


def plotly_network_figure(graph: GraphEnvelope) -> go.Figure:
    """Interactive, dependency-light graph canvas for the Streamlit workbench."""
    positions = _positions(graph)
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for edge in graph.edges:
        source = positions.get(str(edge.get("source")))
        target = positions.get(str(edge.get("target")))
        if not source or not target:
            continue
        edge_x.extend([source[0], target[0], None])
        edge_y.extend([source[1], target[1], None])

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        hoverinfo="skip",
        line={"width": 0.8},
        name="relations",
    )
    node_x, node_y, labels, hover, sizes = [], [], [], [], []
    for node in graph.nodes:
        x, y = positions[str(node["id"])]
        degree = int((node.get("properties") or {}).get("degree") or 0)
        node_x.append(x)
        node_y.append(y)
        labels.append(str(node.get("label") or node["id"]))
        hover.append(
            f"{node.get('type', 'resource')}<br>{(node.get('properties') or {}).get('full_id', node['id'])}"
            f"<br>degree={degree}"
        )
        sizes.append(min(42, 10 + math.sqrt(max(0, degree)) * 3))

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=labels,
        textposition="top center",
        hovertext=hover,
        hoverinfo="text",
        marker={"size": sizes, "line": {"width": 1}},
        name="resources",
    )
    figure = go.Figure(data=[edge_trace, node_trace])
    figure.update_layout(
        height=680,
        showlegend=False,
        hovermode="closest",
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        xaxis={"visible": False},
        yaxis={"visible": False, "scaleanchor": "x", "scaleratio": 1},
        title="Backend-neutral RDF / discourse graph",
    )
    return figure


def jsonld_bytes(graph: GraphEnvelope) -> bytes:
    return json.dumps(jsonld_subgraph(graph), ensure_ascii=False, indent=2).encode("utf-8")
