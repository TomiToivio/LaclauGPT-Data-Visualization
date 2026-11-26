"""One typed multilayer graph for DA, DNA and SNA, built with NetworkX (#330).

The repository already has a renderer-neutral contract (`graph_api.GraphEnvelope`) and separate
readers for the discourse, DNA and SNA products. What was missing is the step between them: a
single graph that can hold any combination of the three layers without melting them together.

Three rules make that safe, and each is a test:

* **A layer is part of identity.** The same string in two layers is two nodes unless an approved
  identity mapping says otherwise. Labels are evidence about a node, never proof that two nodes
  are the same actor — inferring identity from a matching label is exactly the error the issue
  warns about.
* **An edge keeps what it is.** Direction, type, weight, stance/polarity, timestamp and provenance
  travel with the edge. DNA agreement and SNA mention stay different edge types and different
  colours; nothing is averaged into a generic "related".
* **A bounded graph says so.** When a cap drops nodes or edges, the result records how many and
  why. A truncated graph is never presented as the full network.

Node identifiers are stable and typed (`<layer>:<type>:<raw id>`), or `entity:<id>` when an
identity mapping has merged a node across layers. The raw identifier is always kept in the node's
attributes, so a click can still reach the source record.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import networkx as nx

from .graph_api import GraphEnvelope

#: The three discourse layers this module combines, keyed by the contract's names.
LAYER_ALIASES: Mapping[str, str] = {
    "laclau": "da",
    "da": "da",
    "discourse": "da",
    "dna": "dna",
    "sna": "sna",
}

LAYERS = ("da", "dna", "sna")


def layer_of(name: str) -> str | None:
    """Return the layer a contract name refers to, or ``None`` for non-discourse layers."""
    return LAYER_ALIASES.get(str(name).strip().lower())


def node_key(layer: str, node_type: str, raw_id: str) -> str:
    return f"{layer}:{str(node_type).strip()}:{str(raw_id).strip()}"


@dataclass(frozen=True, slots=True)
class MultilayerFilter:
    """Everything a researcher can narrow before the graph is built.

    The filter is a value object so the exact settings can be exported next to a screenshot or a
    GraphML file and reproduce the same view. Empty tuples mean "no restriction", not "nothing".
    """

    layers: tuple[str, ...] = ()
    start: datetime | None = None
    end: datetime | None = None
    platforms: tuple[str, ...] = ()
    actors: tuple[str, ...] = ()
    edge_types: tuple[str, ...] = ()
    empty_signifiers_only: bool = False
    min_weight: float = 0.0

    def normalized(self) -> MultilayerFilter:
        layers = tuple(dict.fromkeys(layer_of(layer) or "" for layer in self.layers))
        layers = tuple(layer for layer in layers if layer in LAYERS)
        return MultilayerFilter(
            layers=layers,
            start=_aware(self.start),
            end=_aware(self.end),
            platforms=tuple(sorted({str(p).strip() for p in self.platforms if str(p).strip()})),
            actors=tuple(sorted({str(a).strip() for a in self.actors if str(a).strip()})),
            edge_types=tuple(sorted({str(t).strip() for t in self.edge_types if str(t).strip()})),
            empty_signifiers_only=bool(self.empty_signifiers_only),
            min_weight=max(0.0, float(self.min_weight)),
        )

    def as_dict(self) -> dict[str, Any]:
        normalized = self.normalized()
        return {
            "layers": list(normalized.layers),
            "start": normalized.start.isoformat() if normalized.start else None,
            "end": normalized.end.isoformat() if normalized.end else None,
            "platforms": list(normalized.platforms),
            "actors": list(normalized.actors),
            "edge_types": list(normalized.edge_types),
            "empty_signifiers_only": normalized.empty_signifiers_only,
            "min_weight": normalized.min_weight,
        }


def _aware(value: datetime | None) -> datetime | None:
    """Canonical record clocks are UTC; a naive filter date is read as UTC, never as local time."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(slots=True)
class MultilayerGraph:
    """A NetworkX multigraph plus the disclosure needed to read it honestly."""

    graph: nx.MultiDiGraph
    filter: MultilayerFilter = field(default_factory=MultilayerFilter)
    truncated: bool = False
    dropped_nodes: int = 0
    dropped_edges: int = 0
    notes: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ reading

    def layers(self) -> dict[str, int]:
        counts = {layer: 0 for layer in LAYERS}
        for _, data in self.graph.nodes(data=True):
            for layer in data.get("layers", ()):
                counts[layer] = counts.get(layer, 0) + 1
        return {layer: count for layer, count in counts.items() if count}

    def nodes_in(self, layer: str) -> list[str]:
        name = layer_of(layer) or layer
        return [
            node for node, data in self.graph.nodes(data=True) if name in data.get("layers", ())
        ]

    def edges_between_layers(self) -> int:
        """Edges whose endpoints come from different layers — the reason to draw one graph."""
        return sum(
            1
            for _, _, data in self.graph.edges(data=True)
            if data.get("layer") == "bridge"
        )

    def disclosure(self) -> dict[str, Any]:
        """What a reader must know before trusting the picture."""
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "layer_counts": self.layers(),
            "truncated": self.truncated,
            "dropped_nodes": self.dropped_nodes,
            "dropped_edges": self.dropped_edges,
            "notes": list(self.notes),
            "filter": self.filter.as_dict(),
        }


def build_multilayer(
    envelope: GraphEnvelope,
    *,
    filter: MultilayerFilter | None = None,
    identity: Mapping[str, str] | None = None,
    max_nodes: int = 500,
    max_edges: int = 2000,
) -> MultilayerGraph:
    """Build the combined graph from a contract envelope.

    ``identity`` maps a raw node identifier to a canonical entity identifier. When two layers name
    the same raw id, providing the mapping merges them into one ``entity:`` node carrying both
    layers; without it they stay separate, which is the conservative default.
    """
    active = (filter or MultilayerFilter()).normalized()
    merged = identity or {}
    notes: list[str] = []

    graph = nx.MultiDiGraph()
    dropped_nodes = dropped_edges = 0

    # A raw id is only unique inside its layer, so the lookup key keeps the layer.
    node_lookup: dict[tuple[str, str], str] = {}
    keys_by_raw: dict[str, set[str]] = {}

    for raw in envelope.nodes:
        layer = layer_of(str(raw.get("layer") or ""))
        if layer is None or (active.layers and layer not in active.layers):
            continue
        raw_id = str(raw.get("id") or "")
        if not raw_id:
            continue
        node_type = str(raw.get("type") or "Node")

        if not _node_matches(raw, active):
            continue

        canonical = merged.get(raw_id)
        if canonical:
            key = f"entity:{canonical}"
        elif raw_id.startswith(("entity:", f"{layer}:")):
            # Already a typed key (this is what to_envelope emits), so rebuilding is idempotent.
            key = raw_id
        else:
            key = node_key(layer, node_type, raw_id)

        node_lookup[(layer, raw_id)] = key
        keys_by_raw.setdefault(raw_id, set()).add(key)
        if graph.number_of_nodes() >= max_nodes and not graph.has_node(key):
            dropped_nodes += 1
            continue

        if graph.has_node(key):
            data = graph.nodes[key]
            data["layers"] = tuple(sorted({*data.get("layers", ()), layer}))
            data.setdefault("raw_ids", {})[layer] = raw_id
            data.setdefault("node_types", set()).add(node_type)
        else:
            properties = dict(raw.get("properties") or {})
            graph.add_node(
                key,
                label=str(raw.get("label") or raw_id),
                layers=(layer,),
                node_types={node_type},
                raw_ids={layer: raw_id},
                layer=layer,
                empty_signifier=bool(properties.get("empty_signifier", False)),
                platform=str(properties.get("platform") or ""),
                provenance_refs=tuple(raw.get("provenance_refs") or ()),
                properties=properties,
            )

    for index, raw in enumerate(envelope.edges):
        layer = layer_of(str(raw.get("layer") or ""))
        if layer is None or (active.layers and layer not in active.layers):
            continue
        source_raw = str(raw.get("source") or "")
        target_raw = str(raw.get("target") or "")
        source = _resolve(node_lookup, keys_by_raw, layer, source_raw)
        target = _resolve(node_lookup, keys_by_raw, layer, target_raw)
        if source is None or target is None or source == target:
            continue
        if not graph.has_node(source) or not graph.has_node(target):
            continue
        if not _edge_matches(raw, active):
            continue
        if graph.number_of_edges() >= max_edges:
            dropped_edges += 1
            continue

        edge_layer = layer
        if set(graph.nodes[source]["layers"]) != set(graph.nodes[target]["layers"]):
            edge_layer = "bridge"
        graph.add_edge(
            source,
            target,
            key=str(raw.get("id") or f"{layer}:edge:{index}"),
            layer=edge_layer,
            declared_layer=layer,
            type=str(raw.get("type") or "related"),
            directed=bool(raw.get("directed", True)),
            weight=float(raw.get("weight") or 1.0),
            polarity=raw.get("polarity"),
            timestamp=_time(raw),
            provenance_refs=tuple(raw.get("provenance_refs") or ()),
            properties=dict(raw.get("properties") or {}),
        )

    if active.start or active.end:
        orphans = [
            node
            for node in graph.nodes()
            if graph.degree(node) == 0 and _time(graph.nodes[node]) is None
        ]
        if orphans:
            graph.remove_nodes_from(orphans)

    if dropped_nodes or dropped_edges:
        notes.append(
            "The graph was capped: "
            f"{dropped_nodes} node(s) and {dropped_edges} edge(s) were left out. "
            "This is a bounded view, not the full network."
        )
    if active.actors or active.platforms or active.start or active.end:
        notes.append("Filters were applied before layout; empty areas are filtered, not missing data.")

    return MultilayerGraph(
        graph=graph,
        filter=active,
        truncated=bool(dropped_nodes or dropped_edges or envelope.truncated),
        dropped_nodes=dropped_nodes,
        dropped_edges=dropped_edges,
        notes=tuple(notes),
        provenance=dict(envelope.provenance),
    )


def _resolve(
    lookup: Mapping[tuple[str, str], str],
    keys_by_raw: Mapping[str, set[str]],
    layer: str,
    raw_id: str,
) -> str | None:
    """Find the node an edge endpoint means, without guessing between ambiguous candidates.

    The endpoint's own layer wins. A cross-layer endpoint is accepted only when the raw id exists in
    exactly one node, because two candidates would be an identity claim the mapping has not made.
    """
    direct = lookup.get((layer, raw_id))
    if direct:
        return direct
    candidates = keys_by_raw.get(raw_id) or set()
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def _node_matches(node: Mapping[str, Any], active: MultilayerFilter) -> bool:
    properties = node.get("properties") or {}
    if active.platforms and str(properties.get("platform") or "") not in active.platforms:
        return False
    if active.actors:
        label = str(node.get("label") or "").casefold()
        raw = str(node.get("id") or "").casefold()
        if not any(actor.casefold() in {label, raw} for actor in active.actors):
            return False
    if active.empty_signifiers_only and not properties.get("empty_signifier"):
        return False
    if active.start or active.end:
        stamp = _time(node)
        # An undated node is undated, not out of range. It survives node filtering and is pruned
        # afterwards only if no surviving edge touches it.
        if stamp is not None:
            if active.start and stamp < active.start:
                return False
            if active.end and stamp > active.end:
                return False
    return True


def _edge_matches(edge: Mapping[str, Any], active: MultilayerFilter) -> bool:
    if active.edge_types and str(edge.get("type") or "") not in active.edge_types:
        return False
    if active.min_weight and float(edge.get("weight") or 1.0) < active.min_weight:
        return False
    if active.start or active.end:
        stamp = _time(edge)
        if stamp is None:
            return False
        if active.start and stamp < active.start:
            return False
        if active.end and stamp > active.end:
            return False
    return True


def _time(item: Mapping[str, Any]) -> datetime | None:
    for holder in (item, item.get("properties") or {}):
        for key in ("timestamp", "published_at", "created_at", "date"):
            value = holder.get(key)
            if not value:
                continue
            if isinstance(value, datetime):
                return _aware(value)
            text = str(value).replace("Z", "+00:00")
            try:
                return _aware(datetime.fromisoformat(text))
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------- metrics


def metrics(graph: nx.MultiDiGraph, *, seed: int = 0) -> dict[str, dict[str, float]]:
    """Descriptive network metrics, computed the same way every time.

    Multi-edges are collapsed for centrality (a repeated mention should not multiply a node's
    standing), and the undirected projection is used for community and betweenness so the result
    does not depend on which way an edge happened to point. These are descriptive observations,
    not evidence of theoretical importance.
    """
    simple = nx.DiGraph()
    simple.add_nodes_from(graph.nodes())
    for source, target, data in graph.edges(data=True):
        weight = float(data.get("weight") or 1.0)
        if simple.has_edge(source, target):
            simple[source][target]["weight"] += weight
        else:
            simple.add_edge(source, target, weight=weight)

    undirected = simple.to_undirected()
    degree = dict(simple.degree())
    weighted = dict(simple.degree(weight="weight"))
    in_degree = dict(simple.in_degree())
    out_degree = dict(simple.out_degree())
    betweenness = (
        nx.betweenness_centrality(undirected, k=min(len(undirected), 200), seed=seed)
        if undirected.number_of_nodes() > 2
        else dict.fromkeys(undirected.nodes(), 0.0)
    )
    communities: dict[str, int] = {}
    for index, group in enumerate(nx.community.greedy_modularity_communities(undirected)):
        for node in group:
            communities[node] = index

    return {
        node: {
            "degree": float(degree.get(node, 0)),
            "weighted_degree": float(weighted.get(node, 0.0)),
            "in_degree": float(in_degree.get(node, 0)),
            "out_degree": float(out_degree.get(node, 0)),
            "betweenness": float(betweenness.get(node, 0.0)),
            "community": float(communities.get(node, -1)),
        }
        for node in graph.nodes()
    }


# ----------------------------------------------------------------------- export


def to_envelope(result: MultilayerGraph) -> GraphEnvelope:
    """Render the built graph back into the contract, so the D3 component reads one shape."""
    nodes = []
    for key, data in result.graph.nodes(data=True):
        nodes.append(
            {
                "id": key,
                "label": data.get("label", key),
                "type": "/".join(sorted(data.get("node_types", ()))),
                "layer": data.get("layer", ""),
                "layers": list(data.get("layers", ())),
                "properties": {
                    **dict(data.get("properties") or {}),
                    "raw_ids": dict(data.get("raw_ids") or {}),
                    "empty_signifier": bool(data.get("empty_signifier")),
                },
                "provenance_refs": list(data.get("provenance_refs") or ()),
            }
        )
    edges = []
    for source, target, key, data in result.graph.edges(keys=True, data=True):
        edges.append(
            {
                "id": key,
                "source": source,
                "target": target,
                "type": data.get("type", "related"),
                # The declared layer, not "bridge": the round trip has to be able to rebuild.
                "layer": data.get("declared_layer") or data.get("layer", ""),
                "cross_layer": data.get("layer") == "bridge",
                "directed": bool(data.get("directed", True)),
                "weight": float(data.get("weight") or 1.0),
                "polarity": data.get("polarity"),
                "timestamp": data["timestamp"].isoformat() if data.get("timestamp") else None,
                "provenance_refs": list(data.get("provenance_refs") or ()),
            }
        )
    return GraphEnvelope(
        nodes=tuple(nodes),
        edges=tuple(edges),
        truncated=result.truncated,
        metadata={
            "layers": result.layers(),
            "disclosure": result.disclosure(),
            "contract": "laclaugpt.graph.v1",
            "multilayer": True,
        },
        provenance=dict(result.provenance),
    )


def write_graphml(result: MultilayerGraph, path: Path) -> Path:
    """Write GraphML for Gephi and friends, with the disclosure kept beside the graph.

    GraphML has no place for a tuple or a set, so layers and raw ids are written as sorted strings
    rather than silently dropped.
    """
    copy = nx.MultiDiGraph()
    for key, data in result.graph.nodes(data=True):
        copy.add_node(
            key,
            label=str(data.get("label", key)),
            layers=",".join(sorted(data.get("layers", ()))),
            node_types=",".join(sorted(data.get("node_types", ()))),
            raw_ids=";".join(f"{layer}={raw}" for layer, raw in sorted((data.get("raw_ids") or {}).items())),
            layer=str(data.get("layer", "")),
        )
    for source, target, key, data in result.graph.edges(keys=True, data=True):
        copy.add_edge(
            source,
            target,
            key=key,
            layer=str(data.get("layer", "")),
            edge_type=str(data.get("type", "related")),
            weight=float(data.get("weight") or 1.0),
            directed=bool(data.get("directed", True)),
            polarity="" if data.get("polarity") is None else str(data["polarity"]),
            timestamp=data["timestamp"].isoformat() if data.get("timestamp") else "",
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(copy, path)
    return path


def ego(result: MultilayerGraph, node: str, *, radius: int = 1) -> MultilayerGraph:
    """One node and its neighbourhood, keeping the original layer semantics."""
    if not result.graph.has_node(node):
        return MultilayerGraph(
            graph=nx.MultiDiGraph(),
            filter=result.filter,
            notes=(f"Node {node} is not in the current graph.",),
            provenance=result.provenance,
        )
    undirected = result.graph.to_undirected(as_view=True)
    reachable = nx.single_source_shortest_path_length(undirected, node, cutoff=max(1, radius))
    keep = set(reachable)
    subgraph = nx.MultiDiGraph()
    for key in keep:
        subgraph.add_node(key, **result.graph.nodes[key])
    for source, target, key, data in result.graph.edges(keys=True, data=True):
        if source in keep and target in keep:
            subgraph.add_edge(source, target, key=key, **data)
    return MultilayerGraph(
        graph=subgraph,
        filter=result.filter,
        truncated=result.truncated,
        notes=(*result.notes, f"Ego network of {node} within {radius} step(s)."),
        provenance=result.provenance,
    )


def expand(result: MultilayerGraph, nodes: Sequence[str], *, layer: str | None = None) -> list[str]:
    """Neighbours of the given nodes, optionally restricted to one layer."""
    found: list[str] = []
    wanted = layer_of(layer) if layer else None
    for node in nodes:
        if not result.graph.has_node(node):
            continue
        for neighbour in nx.all_neighbors(result.graph.to_undirected(as_view=True), node):
            if wanted and wanted not in result.graph.nodes[neighbour].get("layers", ()):
                continue
            if neighbour not in found:
                found.append(neighbour)
    return found


def sorted_edges(result: MultilayerGraph) -> Iterable[tuple[str, str, str]]:
    """Deterministic edge order, so two renders of the same data cannot disagree."""
    yield from sorted(result.graph.edges(keys=True))
