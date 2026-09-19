"""Backend-neutral graph contract for RDF, discourse, DNA and SNA visualization.

This module is deliberately renderer- and database-neutral. Backends return the same
bounded GraphEnvelope; the UI chooses a renderer and never issues backend-specific
queries itself.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

GRAPH_LAYERS = frozenset({"source", "provenance", "laclau", "dna", "sna"})
PHASE2_LAYERS = frozenset({"dna", "sna"})


@dataclass(frozen=True, slots=True)
class GraphQuery:
    roots: tuple[str, ...] = ()
    layers: tuple[str, ...] = ("source", "provenance")
    node_types: tuple[str, ...] = ()
    edge_types: tuple[str, ...] = ()
    study: str | None = None
    collection: str | None = None
    arena: str | None = None
    platform: str | None = None
    language: str | None = None
    region: str | None = None
    start: str | None = None
    end: str | None = None
    depth: int = 1
    max_nodes: int = 250
    max_edges: int = 500
    continuation: str | None = None

    def bounded(self) -> "GraphQuery":
        layers = tuple(layer for layer in self.layers if layer in GRAPH_LAYERS)
        return GraphQuery(
            roots=tuple(self.roots[:50]),
            layers=layers or ("source", "provenance"),
            node_types=tuple(self.node_types[:50]),
            edge_types=tuple(self.edge_types[:50]),
            study=self.study,
            collection=self.collection,
            arena=self.arena,
            platform=self.platform,
            language=self.language,
            region=self.region,
            start=self.start,
            end=self.end,
            depth=max(0, min(int(self.depth), 4)),
            max_nodes=max(1, min(int(self.max_nodes), 1000)),
            max_edges=max(1, min(int(self.max_edges), 2500)),
            continuation=self.continuation,
        )


@dataclass(frozen=True, slots=True)
class GraphEnvelope:
    nodes: tuple[Mapping[str, Any], ...] = ()
    edges: tuple[Mapping[str, Any], ...] = ()
    continuation: str | None = None
    truncated: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], query: GraphQuery) -> "GraphEnvelope":
        bounded = query.bounded()
        nodes = tuple(payload.get("nodes") or ())
        edges = tuple(payload.get("edges") or ())
        if len(nodes) > bounded.max_nodes or len(edges) > bounded.max_edges:
            raise ValueError("graph backend returned an unbounded response")
        return cls(
            nodes=nodes,
            edges=edges,
            continuation=payload.get("continuation"),
            truncated=bool(payload.get("truncated", False)),
            metadata=payload.get("metadata") or {},
            provenance=payload.get("provenance") or {},
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "edges": list(self.edges),
            "continuation": self.continuation,
            "truncated": self.truncated,
            "metadata": dict(self.metadata),
            "provenance": dict(self.provenance),
        }


class GraphBackend(Protocol):
    name: str
    def graph(self, query: GraphQuery) -> GraphEnvelope: ...
    def describe(self, resource_id: str) -> Mapping[str, Any]: ...


def normalize_graph_payload(payload: Mapping[str, Any], query: GraphQuery, *, backend: str) -> GraphEnvelope:
    """Normalize one backend response without changing graph semantics."""
    clean_nodes = []
    for raw in payload.get("nodes") or ():
        node = dict(raw)
        node["id"] = str(node.get("id") or node.get("uri") or "")
        node.setdefault("label", node["id"])
        node.setdefault("type", "Resource")
        node.setdefault("properties", {})
        node.setdefault("provenance_refs", [])
        clean_nodes.append(node)

    clean_edges = []
    for index, raw in enumerate(payload.get("edges") or ()):
        edge = dict(raw)
        edge["source"] = str(edge.get("source") or edge.get("subject") or "")
        edge["target"] = str(edge.get("target") or edge.get("object") or "")
        edge.setdefault("id", f"{backend}:edge:{index}")
        edge.setdefault("type", edge.get("predicate") or "related")
        edge.setdefault("directed", True)
        edge.setdefault("weight", 1.0)
        edge.setdefault("properties", {})
        edge.setdefault("provenance_refs", [])
        clean_edges.append(edge)

    envelope = {
        "nodes": clean_nodes,
        "edges": clean_edges,
        "continuation": payload.get("continuation"),
        "truncated": bool(payload.get("truncated", False)),
        "metadata": {
            **dict(payload.get("metadata") or {}),
            "backend": backend,
            "layers": list(query.bounded().layers),
            "contract": "laclaugpt.graph.v1",
        },
        "provenance": dict(payload.get("provenance") or {}),
    }
    return GraphEnvelope.from_payload(envelope, query)


@dataclass(slots=True)
class LocalGraphBackend:
    """Adapter for local CSV/SQLite-derived graph payloads.

    The caller supplies a bounded payload loader so this class remains independent of
    the concrete persistence library.
    """
    loader: Any
    name: str = "local"

    def graph(self, query: GraphQuery) -> GraphEnvelope:
        bounded = query.bounded()
        return normalize_graph_payload(self.loader(bounded), bounded, backend=self.name)

    def describe(self, resource_id: str) -> Mapping[str, Any]:
        if hasattr(self.loader, "describe"):
            return self.loader.describe(resource_id)
        return {"id": resource_id}


@dataclass(slots=True)
class MongoGraphBackend:
    """Adapter around a Mongo-backed query object, injected for testability."""
    provider: Any
    name: str = "mongodb"

    def graph(self, query: GraphQuery) -> GraphEnvelope:
        bounded = query.bounded()
        payload = self.provider.graph_payload(bounded)
        return normalize_graph_payload(payload, bounded, backend=self.name)

    def describe(self, resource_id: str) -> Mapping[str, Any]:
        return self.provider.describe(resource_id)


@dataclass(slots=True)
class ArangoGraphBackend:
    """Optional ArangoDB adapter without importing an Arango driver.

    A tiny provider interface is injected so Arango remains optional and no connection
    occurs at import time.
    """
    provider: Any
    name: str = "arangodb"

    def graph(self, query: GraphQuery) -> GraphEnvelope:
        bounded = query.bounded()
        payload = self.provider.traverse(bounded)
        return normalize_graph_payload(payload, bounded, backend=self.name)

    def describe(self, resource_id: str) -> Mapping[str, Any]:
        return self.provider.describe(resource_id)


def layer_enabled(layer: str, *, phase: int) -> bool:
    """Phase-safe layer gate. Phase-2 analytical layers stay dormant before phase 2."""
    return layer in GRAPH_LAYERS and not (layer in PHASE2_LAYERS and phase < 2)


def evidence_refs(item: Mapping[str, Any]) -> tuple[str, ...]:
    refs = item.get("provenance_refs") or item.get("evidence_refs") or ()
    if isinstance(refs, str):
        return (refs,)
    return tuple(str(ref) for ref in refs if ref)


def jsonld_subgraph(graph: GraphEnvelope) -> dict[str, Any]:
    """Portable selected-subgraph export; intentionally not an ontology editor."""
    by_id = {str(node.get("id")): node for node in graph.nodes}
    result = []
    for node_id, node in by_id.items():
        record = {
            "@id": node_id,
            "@type": node.get("type", "Resource"),
            "label": node.get("label", node_id),
            **dict(node.get("properties") or {}),
        }
        outgoing = [e for e in graph.edges if str(e.get("source")) == node_id]
        for edge in outgoing:
            predicate = str(edge.get("predicate") or edge.get("type") or "related")
            record.setdefault(predicate, []).append({"@id": str(edge.get("target"))})
        result.append(record)
    return {"@graph": result}
