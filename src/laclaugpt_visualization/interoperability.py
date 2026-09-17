"""Renderer-neutral DATS/DNA visualization interoperability.

The Analysis module owns analytical construction.  This module consumes portable
objects and produces view models/export artefacts without inferring discourse-
theoretical conclusions from visual/network structure.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping
from xml.etree.ElementTree import Element, SubElement, tostring

SEMANTIC_SAFEGUARDS = (
    "graph degree != nodal point",
    "visual centrality != hegemony",
    "community/cluster != ideological formation",
    "actor agreement != Laclauian equivalence",
    "negative/conflict edge != antagonistic frontier by itself",
    "semantic proximity != equivalence",
    "topic prevalence != hegemony",
    "two clusters != polarization without an explicit operationalization",
    "decorative layout distance != semantic distance",
)


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    source_url: str
    evidence_id: str | None = None
    statement_id: str | None = None
    annotation_id: str | None = None
    external_ids: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ViewNode:
    id: str
    label: str
    node_type: str
    external_ids: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)
    review_status: str | None = None
    uncertainty: str | None = None
    evidence: tuple[EvidenceLink, ...] = ()


@dataclass(frozen=True, slots=True)
class ViewEdge:
    id: str
    source: str
    target: str
    edge_type: str
    weight: float = 1.0
    directed: bool = False
    attributes: dict[str, Any] = field(default_factory=dict)
    review_status: str | None = None
    uncertainty: str | None = None
    evidence: tuple[EvidenceLink, ...] = ()


@dataclass(frozen=True, slots=True)
class GraphViewModel:
    projection_id: str
    graph_type: str
    node_semantics: str
    edge_semantics: str
    projection_method: str
    weighting_method: str
    nodes: tuple[ViewNode, ...]
    edges: tuple[ViewEdge, ...]
    temporal_scope: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)
    producer: dict[str, Any] = field(default_factory=dict)
    provenance_id: str | None = None
    source_analysis_run: str | None = None
    safeguards: tuple[str, ...] = SEMANTIC_SAFEGUARDS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _external_ids(value: Any) -> dict[str, str]:
    if isinstance(value, Mapping):
        return {str(k): str(v) for k, v in value.items()}
    result: dict[str, str] = {}
    for ref in value or []:
        if isinstance(ref, Mapping) and ref.get("system") is not None and ref.get("id") is not None:
            result[str(ref["system"])] = str(ref["id"])
    return result


def dats_review_view(project: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize DATS interchange objects for Monitor/Review/Explore plugins."""
    documents = []
    doc_urls: dict[str, str] = {}
    for doc in project.get("documents", []):
        doc_id = str(doc.get("id") or doc.get("source_url"))
        source_url = str(doc.get("source_url") or f"dats:document:{doc_id}")
        doc_urls[doc_id] = source_url
        documents.append({
            "id": doc_id,
            "source_url": source_url,
            "title": doc.get("title"),
            "text": doc.get("text", ""),
            "language": doc.get("language"),
            "external_ids": {"dats": doc_id},
        })

    codes = [{
        "id": str(code.get("canonical_id") or code.get("id")),
        "label": str(code.get("label", "")),
        "parent_id": code.get("parent_id"),
        "description": code.get("description"),
        "external_ids": {"dats": str(code.get("id"))},
    } for code in project.get("codes", [])]

    annotations = []
    for ann in project.get("annotations", []):
        producer_type = str(ann.get("producer_type", "human"))
        status = str(ann.get("review_status") or ("ACCEPTED" if producer_type == "human" else "PROVISIONAL"))
        document_id = str(ann.get("document_id"))
        annotations.append({
            "id": str(ann.get("canonical_id") or ann.get("id")),
            "document_id": document_id,
            "source_url": doc_urls.get(document_id, str(ann.get("source_url", ""))),
            "code_id": str(ann.get("code_id", "")),
            "start": ann.get("start"),
            "end": ann.get("end"),
            "producer_type": producer_type,
            "producer_id": str(ann.get("producer_id", "unknown")),
            "review_status": status,
            "confidence": ann.get("confidence"),
            "machine_generated": producer_type == "model",
            "external_ids": {"dats": str(ann.get("id"))},
        })

    return {
        "schema_version": "visualization-interop-v1",
        "source_tool": "dats",
        "project_id": str(project.get("project_id", "dats-project")),
        "documents": documents,
        "codes": codes,
        "annotations": annotations,
        "notes": list(project.get("notes", project.get("memos", [])) or []),
        "temporal_series": list(project.get("temporal_series", [])),
        "relations": list(project.get("relations", [])),
        "safeguards": list(SEMANTIC_SAFEGUARDS),
    }


def export_dats_review(view: Mapping[str, Any]) -> dict[str, Any]:
    """Export review-compatible DATS objects without upgrading AI proposals to human coding."""
    annotations = []
    for ann in view.get("annotations", []):
        producer_type = str(ann.get("producer_type", "human"))
        review_status = str(ann.get("review_status", "PROVISIONAL"))
        annotations.append({
            "id": _external_ids(ann.get("external_ids", {})).get("dats", ann.get("id")),
            "document_id": ann.get("document_id"),
            "code_id": ann.get("code_id"),
            "start": ann.get("start"),
            "end": ann.get("end"),
            "producer_type": producer_type,
            "producer_id": ann.get("producer_id"),
            "review_status": review_status,
            "provisional_ai": producer_type == "model" and review_status == "PROVISIONAL",
            "confidence": ann.get("confidence"),
        })
    return {
        "schema_version": "visualization-interop-v1",
        "project_id": view.get("project_id"),
        "annotations": annotations,
        "notes": list(view.get("notes", [])),
        "relations": list(view.get("relations", [])),
    }


def dna_graph_view(
    statements: Iterable[Mapping[str, Any]],
    projection: Mapping[str, Any],
) -> GraphViewModel:
    """Build an actor-concept semantic view from Analysis DiscourseStatement objects."""
    actor_nodes: dict[str, ViewNode] = {}
    concept_nodes: dict[str, ViewNode] = {}
    edges: list[ViewEdge] = []
    for raw in statements:
        sid = str(raw["statement_id"])
        actor_id = str(raw["actor_id"])
        concept_id = str(raw["concept_id"])
        external = _external_ids(raw.get("external_ids"))
        evidence = EvidenceLink(
            source_url=str(raw["source_url"]),
            evidence_id=raw.get("evidence_id"),
            statement_id=sid,
            external_ids=external,
        )
        actor_nodes.setdefault(actor_id, ViewNode(
            id=actor_id,
            label=str(raw.get("actor_label", actor_id)),
            node_type="actor",
            attributes=dict(raw.get("actor_attributes", {})),
            evidence=(evidence,),
        ))
        concept_nodes.setdefault(concept_id, ViewNode(
            id=concept_id,
            label=str(raw.get("concept_label", concept_id)),
            node_type="concept",
            evidence=(evidence,),
        ))
        qualifier = raw.get("qualifier")
        edges.append(ViewEdge(
            id=sid,
            source=actor_id,
            target=concept_id,
            edge_type="actor-concept statement",
            weight=1.0,
            directed=False,
            attributes={"qualifier": qualifier, "timestamp": raw.get("timestamp")},
            review_status=raw.get("review_status"),
            uncertainty=raw.get("uncertainty"),
            evidence=(evidence,),
        ))

    producer = projection.get("producer") or {}
    return GraphViewModel(
        projection_id=str(projection["projection_id"]),
        graph_type=str(projection.get("graph_type", "actor_concept_bipartite")),
        node_semantics=str(projection.get("node_semantics", "actors and coded concepts")),
        edge_semantics=str(projection.get("edge_semantics", "coded actor-concept statements")),
        projection_method=str(projection.get("projection_method", "statement affiliation")),
        weighting_method=str(projection.get("weighting_method", "statement count")),
        nodes=tuple(actor_nodes.values()) + tuple(concept_nodes.values()),
        edges=tuple(edges),
        temporal_scope=dict(projection.get("temporal_scope", {})),
        filters=dict(projection.get("parameters", {}).get("filters", {})),
        producer=dict(producer),
        provenance_id=projection.get("provenance_id"),
        source_analysis_run=projection.get("source_analysis_run"),
    )


def graph_json(view: GraphViewModel) -> str:
    return json.dumps(view.to_dict(), ensure_ascii=False, sort_keys=True, indent=2)


def node_edge_csv(view: GraphViewModel) -> tuple[str, str]:
    node_buf, edge_buf = io.StringIO(), io.StringIO()
    nw = csv.DictWriter(node_buf, fieldnames=["id", "label", "node_type", "review_status", "uncertainty", "external_ids"])
    nw.writeheader()
    for node in view.nodes:
        nw.writerow({
            "id": node.id, "label": node.label, "node_type": node.node_type,
            "review_status": node.review_status or "", "uncertainty": node.uncertainty or "",
            "external_ids": json.dumps(node.external_ids, ensure_ascii=False, sort_keys=True),
        })
    ew = csv.DictWriter(edge_buf, fieldnames=["id", "source", "target", "edge_type", "weight", "directed", "review_status", "uncertainty"])
    ew.writeheader()
    for edge in view.edges:
        ew.writerow({
            "id": edge.id, "source": edge.source, "target": edge.target,
            "edge_type": edge.edge_type, "weight": edge.weight, "directed": edge.directed,
            "review_status": edge.review_status or "", "uncertainty": edge.uncertainty or "",
        })
    return node_buf.getvalue(), edge_buf.getvalue()


def _graph_xml(view: GraphViewModel, *, gexf: bool) -> str:
    if gexf:
        root = Element("gexf", {"xmlns": "http://www.gexf.net/1.3", "version": "1.3"})
        graph = SubElement(root, "graph", {"mode": "static", "defaultedgetype": "directed" if any(e.directed for e in view.edges) else "undirected"})
        meta = SubElement(graph, "meta")
        meta.text = json.dumps({"projection_id": view.projection_id, "node_semantics": view.node_semantics, "edge_semantics": view.edge_semantics, "projection_method": view.projection_method, "weighting_method": view.weighting_method, "temporal_scope": view.temporal_scope, "filters": view.filters, "producer": view.producer, "provenance_id": view.provenance_id}, ensure_ascii=False, sort_keys=True)
        nodes_el, edges_el = SubElement(graph, "nodes"), SubElement(graph, "edges")
        for node in view.nodes:
            SubElement(nodes_el, "node", {"id": node.id, "label": node.label, "type": node.node_type})
        for edge in view.edges:
            SubElement(edges_el, "edge", {"id": edge.id, "source": edge.source, "target": edge.target, "weight": str(edge.weight), "type": edge.edge_type})
    else:
        root = Element("graphml", {"xmlns": "http://graphml.graphdrawing.org/xmlns"})
        graph = SubElement(root, "graph", {"id": view.projection_id, "edgedefault": "directed" if any(e.directed for e in view.edges) else "undirected"})
        meta = SubElement(graph, "data", {"key": "semantic_metadata"})
        meta.text = json.dumps({"graph_type": view.graph_type, "node_semantics": view.node_semantics, "edge_semantics": view.edge_semantics, "projection_method": view.projection_method, "weighting_method": view.weighting_method, "temporal_scope": view.temporal_scope, "filters": view.filters, "producer": view.producer, "provenance_id": view.provenance_id}, ensure_ascii=False, sort_keys=True)
        for node in view.nodes:
            item = SubElement(graph, "node", {"id": node.id})
            SubElement(item, "data", {"key": "label"}).text = node.label
            SubElement(item, "data", {"key": "node_type"}).text = node.node_type
        for edge in view.edges:
            item = SubElement(graph, "edge", {"id": edge.id, "source": edge.source, "target": edge.target})
            SubElement(item, "data", {"key": "edge_type"}).text = edge.edge_type
            SubElement(item, "data", {"key": "weight"}).text = str(edge.weight)
    return tostring(root, encoding="unicode")


def graphml_dumps(view: GraphViewModel) -> str:
    return _graph_xml(view, gexf=False)


def gexf_dumps(view: GraphViewModel) -> str:
    return _graph_xml(view, gexf=True)


def renderer_payload(view: GraphViewModel, renderer: str = "cytoscape") -> dict[str, Any]:
    """Thin replaceable browser payload; semantic view model remains authoritative."""
    renderer = renderer.casefold()
    if renderer == "cytoscape":
        return {"renderer": "cytoscape", "elements": {
            "nodes": [{"data": {"id": n.id, "label": n.label, "node_type": n.node_type, "review_status": n.review_status, "uncertainty": n.uncertainty}} for n in view.nodes],
            "edges": [{"data": {"id": e.id, "source": e.source, "target": e.target, "edge_type": e.edge_type, "weight": e.weight, "review_status": e.review_status, "uncertainty": e.uncertainty}} for e in view.edges],
        }, "metadata": _renderer_metadata(view)}
    if renderer in {"sigma", "graphology"}:
        return {"renderer": "sigma", "nodes": [{"key": n.id, "attributes": {"label": n.label, "node_type": n.node_type}} for n in view.nodes], "edges": [{"key": e.id, "source": e.source, "target": e.target, "attributes": {"type": e.edge_type, "weight": e.weight}} for e in view.edges], "metadata": _renderer_metadata(view)}
    raise ValueError(f"Unsupported renderer: {renderer}")


def _renderer_metadata(view: GraphViewModel) -> dict[str, Any]:
    return {
        "projection_id": view.projection_id,
        "graph_type": view.graph_type,
        "node_semantics": view.node_semantics,
        "edge_semantics": view.edge_semantics,
        "projection_method": view.projection_method,
        "weighting_method": view.weighting_method,
        "temporal_scope": view.temporal_scope,
        "filters": view.filters,
        "producer": view.producer,
        "provenance_id": view.provenance_id,
        "safeguards": list(view.safeguards),
    }


def vega_lite_spec(rows: list[Mapping[str, Any]], *, x: str, y: str, mark: str = "line", color: str | None = None, title: str | None = None) -> dict[str, Any]:
    """Portable Vega-Lite chart contract for Python/R/browser handoff."""
    encoding: dict[str, Any] = {"x": {"field": x}, "y": {"field": y, "type": "quantitative"}}
    if color:
        encoding["color"] = {"field": color, "type": "nominal"}
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "Renderer-neutral LaclauGPT chart. Visual prominence is descriptive, not a theoretical conclusion.",
        "title": title,
        "data": {"values": [dict(row) for row in rows]},
        "mark": mark,
        "encoding": encoding,
        "usermeta": {"safeguards": list(SEMANTIC_SAFEGUARDS)},
    }
