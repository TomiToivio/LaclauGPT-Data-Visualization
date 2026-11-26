"""AI26 evidence-linked multilayer display adapter, independent of Streamlit and storage.

The producer owns all theoretical classifications, social ties and identity decisions.
NetworkX only organizes explicit records/edges for the bounded on-screen graph.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from itertools import zip_longest
from typing import Any

import networkx as nx
import pandas as pd

LAYERS = ("da", "dna", "sna")
_LAYER = {"laclau": "da", "da": "da", "dna": "dna", "sna": "sna"}
_OBJECT_GROUPS = {
    "entities": "actor",
    "themes": "theme",
    "signifiers": "signifier",
    "nodal_points": "nodal-point",
    "floating_signifiers": "floating-signifier",
    "empty_signifier_candidates": "empty-signifier candidate",
    "formations": "formation",
    "imaginaries": "imaginary",
    "collective_subjects": "collective-subject",
    "them": "other",
    "frontier": "frontier",
    "affects": "affect",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _analysis(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_mapping(record.get("raw_record")).get("analysis"))


def coded_labels(record: Mapping[str, Any], field: str) -> set[str]:
    """Only producer-coded objects; ordinary signifiers are not empty-signifier candidates."""
    return {
        label for item in _rows(_analysis(record).get(field)) if (label := _text(item.get("label")))
    }


def filter_coded_records(
    frame: pd.DataFrame,
    *,
    actors: tuple[str, ...] = (),
    empty_signifiers: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Match the exact producer-coded label, not username or arbitrary fulltext."""
    for field, selected in (("entities", actors), ("empty_signifier_candidates", empty_signifiers)):
        if selected:
            wanted = set(selected)
            mask = [bool(wanted & coded_labels(row, field)) for row in frame.to_dict("records")]
            frame = frame.loc[mask]
    return frame


def period_bounds(
    preset: str,
    *,
    selected_start: Any = None,
    selected_end: Any = None,
    now: datetime | None = None,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Half-open UTC interval: exact day, calendar week, rolling window, or custom dates."""
    moment = pd.Timestamp(now or datetime.now(UTC))
    moment = moment.tz_localize("UTC") if moment.tzinfo is None else moment.tz_convert("UTC")
    if preset == "All loaded dates":
        return None, None
    if preset in ("Last 24 hours", "Last 7 days"):
        return moment - pd.Timedelta(days=1 if preset == "Last 24 hours" else 7), moment
    day = pd.Timestamp(selected_start or moment.date())
    day = day.tz_localize("UTC") if day.tzinfo is None else day.tz_convert("UTC")
    day = day.normalize()
    if preset == "Selected UTC day":
        return day, day + pd.Timedelta(days=1)
    if preset == "Selected UTC week":
        monday = day - pd.Timedelta(days=day.weekday())
        return monday, monday + pd.Timedelta(days=7)
    if preset != "Custom UTC dates":
        raise ValueError("Unknown date preset")
    last = pd.Timestamp(selected_end or day.date())
    last = last.tz_localize("UTC") if last.tzinfo is None else last.tz_convert("UTC")
    end = last.normalize() + pd.Timedelta(days=1)
    if end <= day:
        raise ValueError("End date must be on or after start date")
    return day, end


def filter_publication_window(
    frame: pd.DataFrame,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> pd.DataFrame:
    """Use source timestamps only; never substitute collection or analysis times."""
    if start is None and end is None:
        return frame
    times = pd.to_datetime(
        frame.get("source_timestamp", pd.Series(index=frame.index, dtype="object")),
        utc=True,
        errors="coerce",
        format="mixed",
    )
    mask = times.notna()
    if start is not None:
        mask &= times >= start
    if end is not None:
        mask &= times < end
    return frame.loc[mask]


def _identity(kind: str, producer_id: str) -> str:
    # Analysis documents actor/concept namespaces as shared across method layers.
    # Use exact producer IDs, never display labels or fuzzy matching.
    if kind == "actor":
        namespace = "actor"
    elif kind in {*_OBJECT_GROUPS.values(), "empty-signifier", "dna-concept", "concept"}:
        namespace = "concept"
    else:
        namespace = kind
    return f"{namespace}:{producer_id}"


def _node(node_id: str, kind: str, label: str, layer: str, **extra: Any) -> dict[str, Any]:
    return {"id": node_id, "kind": kind, "label": label, "layers": [layer], **extra}


def _add_node(nodes: dict[str, dict[str, Any]], item: dict[str, Any]) -> None:
    existing = nodes.setdefault(item["id"], item)
    if existing is not item:
        existing["layers"] = sorted(set(existing["layers"] + item["layers"]))


def _record_edges(
    frame: pd.DataFrame,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in frame.to_dict("records"):
        source_url = _text(row.get("source_url"))
        if not source_url:
            continue
        analysis = _analysis(row)
        by_reference: dict[str, str] = {}
        for field, kind in _OBJECT_GROUPS.items():
            for item in _rows(analysis.get(field)):
                ref = _text(item.get("entity_id") or item.get("object_id"))
                if not ref:
                    continue
                node_id = _identity(kind, ref)
                by_reference.setdefault(ref, node_id)
                _add_node(nodes, _node(node_id, kind, _text(item.get("label")) or ref, "da"))
        for field in ("relations", "antagonisms", "actor_entity_relations"):
            for relation in _rows(analysis.get(field)):
                ref = _text(relation.get("relation_id"))
                src = _text(relation.get("source_ref"))
                dst = _text(relation.get("target_ref"))
                kind = _text(relation.get("relation_type"))
                if not all((src, dst, ref, kind)) or (source_url, ref) in seen:
                    continue
                seen.add((source_url, ref))
                for endpoint in (src, dst):
                    if endpoint not in by_reference:
                        # Unknown endpoint is a source-scoped reference, never a guessed entity.
                        node_id = f"reference:{source_url}:{endpoint}"
                        by_reference[endpoint] = node_id
                        _add_node(nodes, _node(node_id, "reference", endpoint, "da"))
                edges.append(
                    {
                        "id": f"da:{source_url}:{ref}",
                        "source": by_reference[src],
                        "target": by_reference[dst],
                        "layer": "da",
                        "type": kind,
                        "weight": relation.get("weight"),
                        "directed": True,
                        "assertion_kind": "coded",
                        "source_url": source_url,
                        "provenance": {
                            "evidence_ids": relation.get("evidence_ids") or [],
                            "provenance_id": relation.get("provenance_id"),
                        },
                        "review_status": relation.get("review_status"),
                        "timestamp": str(row.get("source_timestamp") or ""),
                    }
                )
    return nodes, edges


def _safe_provenance(provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Allow only fields in the producer GraphProvenance contract into browser payloads."""
    scalars = (
        "source_id",
        "source_url",
        "run_id",
        "provenance_id",
        "method",
        "model",
        "config_id",
        "transformation",
    )
    result = {key: value for key in scalars if isinstance(value := provenance.get(key), str)}
    for key in ("evidence_ids", "codebook_refs"):
        values = provenance.get(key)
        if isinstance(values, list):
            result[key] = [value for value in values if isinstance(value, str)]
    return result


def _artifact_edges(
    payload: Mapping[str, Any],
    sources: set[str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], int]:
    """Read the Analysis v1 AnalyticalGraph (not a locally inferred projection)."""
    if payload.get("schema_version") != "1.0.0":
        raise ValueError("Expected an Analysis AnalyticalGraph 1.0.0 export")
    if str(payload.get("project_id", "")).casefold() != "ai26":
        raise ValueError("AnalyticalGraph project must be AI26")
    if not isinstance(payload.get("nodes"), list) or not isinstance(payload.get("edges"), list):
        raise TypeError("AnalyticalGraph must contain nodes and edges arrays")
    nodes: dict[str, dict[str, Any]] = {}
    references: dict[str, str] = {}
    for node in _rows(payload["nodes"]):
        ref = _text(node.get("id"))
        kind = _text(node.get("kind"))
        if not ref or not kind or kind.startswith("derived-"):
            continue
        node_id = _identity(kind, ref)
        if ref in references and references[ref] != node_id:
            raise ValueError("Conflicting typed identity in upstream graph")
        references[ref] = node_id
        layer = _LAYER.get(node.get("layer"), "source")
        _add_node(
            nodes,
            _node(
                node_id,
                kind,
                _text(node.get("label")) or ref,
                layer,
                uri=node.get("uri"),
            ),
        )
    edges: list[dict[str, Any]] = []
    omitted = 0
    seen: set[str] = set()
    for edge in _rows(payload["edges"]):
        layer = _LAYER.get(edge.get("layer"))
        if layer is None or edge.get("assertion_kind") == "graph-statistical":
            continue
        provenance = _mapping(edge.get("provenance"))
        source_url = _text(provenance.get("source_url"))
        if not source_url:
            omitted += 1
            continue
        if source_url not in sources:
            continue
        src = references.get(edge.get("source"))
        dst = references.get(edge.get("target"))
        edge_id = _text(edge.get("id"))
        if not src or not dst or not edge_id:
            omitted += 1
            continue
        identifier = f"{layer}:{edge_id}"
        if identifier in seen:
            raise ValueError("Duplicate analytical edge identity")
        seen.add(identifier)
        properties = _mapping(edge.get("properties"))
        edges.append(
            {
                "id": identifier,
                "source": src,
                "target": dst,
                "type": edge.get("kind"),
                "layer": layer,
                "weight": edge.get("weight"),
                "directed": edge.get("directed") is True,
                "assertion_kind": edge.get("assertion_kind"),
                "source_url": source_url,
                "provenance": _safe_provenance(provenance),
                "review_status": properties.get("review_status"),
                "stance": properties.get("qualifier") or properties.get("stance"),
                "timestamp": edge.get("valid_from"),
                "valid_to": edge.get("valid_to"),
                "snapshot_id": edge.get("snapshot_id"),
            }
        )
    return nodes, edges, omitted


def graph_view(
    frame: pd.DataFrame,
    artifact: Mapping[str, Any] | None = None,
    *,
    layers: tuple[str, ...] = LAYERS,
    max_nodes: int = 250,
    max_edges: int = 500,
    min_weight: float = 0,
    edge_types: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build a bounded NetworkX multigraph; degree means visible incident edges only.

    This record-backed adapter does not invoke the generic GraphEnvelope-only
    multilayer builder: its source-level filtering is shared with dashboard charts,
    and explicit stable actor/concept IDs supplied by Analysis are the identity map.
    """
    nodes, edges = _record_edges(frame)
    omitted = 0
    if artifact is not None:
        upstream_nodes, upstream_edges, omitted = _artifact_edges(
            artifact,
            {_text(url) for url in frame.get("source_url", [])},
        )
        # Prefer the upstream DA projection for each covered source, to avoid double counting.
        da_sources = {edge["source_url"] for edge in upstream_edges if edge["layer"] == "da"}
        edges = [edge for edge in edges if edge["source_url"] not in da_sources]
        for item in upstream_nodes.values():
            _add_node(nodes, item)
        edges.extend(upstream_edges)
    available = {layer: sum(edge["layer"] == layer for edge in edges) for layer in LAYERS}
    selected = [
        edge
        for edge in edges
        if edge["layer"] in layers
        and (not edge_types or edge["type"] in edge_types)
        and (
            min_weight == 0
            or (isinstance(edge["weight"], (int, float)) and edge["weight"] >= min_weight)
        )
    ]
    # Stable ordering, no hidden weighting of research significance. Bounds retain full endpoints.
    groups = [
        sorted((edge for edge in selected if edge["layer"] == layer), key=lambda edge: edge["id"])
        for layer in LAYERS
    ]
    # Interleave layers so a large DA graph cannot crowd out all DNA/SNA edges.
    ordered = [edge for batch in zip_longest(*groups) for edge in batch if edge is not None]
    graph = nx.MultiDiGraph()
    visible: list[dict[str, Any]] = []
    for edge in ordered:
        endpoints = {edge["source"], edge["target"]}
        if len(visible) >= max_edges:
            break
        if len(set(graph.nodes) | endpoints) > max_nodes:
            continue
        graph.add_edge(edge["source"], edge["target"], key=edge["id"])
        visible.append(edge)
    display_nodes = []
    for node_id in sorted(graph.nodes):
        item = dict(nodes[node_id])
        item["layers"] = sorted(
            {edge["layer"] for edge in visible if node_id in (edge["source"], edge["target"])}
        )
        item["degree"] = int(graph.degree(node_id))
        display_nodes.append(item)
    return {
        "nodes": display_nodes,
        "edges": visible,
        "availability": available,
        "matched_edges": len(selected),
        "truncated": len(visible) != len(selected),
        "omitted_unlinked_edges": omitted,
        "input_truncated": bool(artifact and artifact.get("input_truncated")),
        "filters": {
            "layers": list(layers),
            "edge_types": list(edge_types),
            "min_weight": min_weight,
            "max_nodes": max_nodes,
            "max_edges": max_edges,
        },
    }


def load_mongo_artifact(
    database: Any,
    sources: set[str],
    *,
    limit: int = 5000,
) -> dict[str, Any] | None:
    """Read the documented Analysis MongoGraphStore, with the same source window as charts.

    The bound is applied **per layer**, not once over the whole collection. One global id-ordered
    limit silently erases a layer: the DNA projection contributes three edges per coded statement,
    so in a large window it fills the budget and the smaller SNA layer, whose edge ids happen to
    sort last, arrives as zero. The dashboard then reports "0 SNA edges" for a project that has
    them. Each layer keeps its own deterministic window and reports its own truncation.
    """
    if not sources:
        return None
    # Analysis examples use both spellings. Never combine two distinct project graphs.
    meta = database["kg_meta"].find_one({"project_id": "ai26"}, {"_id": 0})
    if meta is None:
        meta = database["kg_meta"].find_one({"project_id": "AI26"}, {"_id": 0})
    if meta is None:
        return None
    project_id = meta["project_id"]
    query = {"project_id": project_id, "provenance.source_url": {"$in": sorted(sources)}}
    edges: list[dict[str, Any]] = []
    truncated = False
    for layer in LAYERS:
        rows = list(
            database["kg_edges"]
            .find({**query, "layer": layer}, {"_id": 0})
            .sort("id", 1)
            .limit(limit + 1)
        )
        if len(rows) > limit:
            truncated = True
            rows = rows[:limit]
        edges.extend(rows)
    ids = sorted(
        {
            ref
            for edge in edges
            for ref in (edge.get("source"), edge.get("target"))
            if isinstance(ref, str)
        }
    )
    nodes = list(
        database["kg_nodes"].find(
            {"project_id": project_id, "id": {"$in": ids}},
            {"_id": 0},
        )
    )
    return {**meta, "nodes": nodes, "edges": edges, "input_truncated": truncated}
