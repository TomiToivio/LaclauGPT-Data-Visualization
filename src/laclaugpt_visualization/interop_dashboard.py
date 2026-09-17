"""Dashboard-facing adapters for DATS/DNA interoperability.

These helpers bridge portable Analysis/DATS/DNA objects into the normal LaclauGPT
research workflow without making renderer-specific structures canonical.  Analytical
inference remains upstream; this module only normalizes data for review, tables,
exports and semantic graph rendering.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from .interoperability import (
    EvidenceLink,
    GraphViewModel,
    SEMANTIC_SAFEGUARDS,
    ViewEdge,
    ViewNode,
    dats_review_view,
)


def dats_dashboard_frame(project: Mapping[str, Any]) -> pd.DataFrame:
    """Convert DATS interchange data into the normal researcher dataframe surface.

    One row is emitted per source document. DATS annotations remain structured evidence
    on the row so Monitor / Researcher Review / Explore can consume the same dataframe
    shape instead of requiring a DATS-only application.
    """
    view = dats_review_view(project)
    annotations_by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for annotation in view["annotations"]:
        annotations_by_document[str(annotation.get("document_id", ""))].append(annotation)

    rows: list[dict[str, Any]] = []
    for document in view["documents"]:
        document_id = str(document["id"])
        annotations = annotations_by_document.get(document_id, [])
        review_states = {str(item.get("review_status", "")) for item in annotations}
        machine_generated = any(bool(item.get("machine_generated")) for item in annotations)
        rows.append(
            {
                "source_url": document["source_url"],
                "source_platform": "dats",
                "source_language": document.get("language") or "",
                "source_author": "",
                "summary": document.get("title") or document_id,
                "text": document.get("text") or "",
                "entities": [],
                "topics": [],
                "formations": [],
                "signifiers": [],
                "relations": list(view.get("relations", [])),
                "evidence": annotations,
                "external_ids": document.get("external_ids", {}),
                "interop_source_tool": "dats",
                "interop_document_id": document_id,
                "review_status": _aggregate_review_state(review_states),
                "machine_generated": machine_generated,
                "research_notes": list(view.get("notes", [])),
                "temporal_series": list(view.get("temporal_series", [])),
                "visualization_safeguards": list(SEMANTIC_SAFEGUARDS),
            }
        )
    return pd.DataFrame(rows)


def graph_projection_view(projection: Mapping[str, Any]) -> GraphViewModel:
    """Consume an Analysis-owned GraphProjection with precomputed nodes and edges.

    This is the generic path for actor congruence/conflict, concept, temporal/windowed,
    coalition/community and other upstream projections. The dashboard does not recompute
    those analytical structures.
    """
    nodes = tuple(_node_from_mapping(item) for item in projection.get("nodes", ()))
    edges = tuple(_edge_from_mapping(item) for item in projection.get("edges", ()))
    parameters = projection.get("parameters") or {}
    filters = projection.get("filters") or (
        parameters.get("filters", {}) if isinstance(parameters, Mapping) else {}
    )
    return GraphViewModel(
        projection_id=str(projection.get("projection_id") or "projection"),
        graph_type=str(projection.get("graph_type") or "generic"),
        node_semantics=str(projection.get("node_semantics") or "explicit upstream nodes"),
        edge_semantics=str(projection.get("edge_semantics") or "explicit upstream relations"),
        projection_method=str(projection.get("projection_method") or "upstream-defined"),
        weighting_method=str(projection.get("weighting_method") or "upstream-defined"),
        nodes=nodes,
        edges=edges,
        temporal_scope=dict(projection.get("temporal_scope") or {}),
        filters=dict(filters) if isinstance(filters, Mapping) else {},
        producer=dict(projection.get("producer") or {}),
        provenance_id=projection.get("provenance_id"),
        source_analysis_run=projection.get("source_analysis_run"),
    )


def graph_measure_table(projection: Mapping[str, Any]) -> pd.DataFrame:
    """Return precomputed network measures as a researcher table.

    No centrality/community calculation happens here; only upstream results are exposed.
    """
    measures = projection.get("measures") or projection.get("network_measures") or []
    if isinstance(measures, Mapping):
        measures = [
            {"element_id": element_id, **(dict(values) if isinstance(values, Mapping) else {"value": values})}
            for element_id, values in measures.items()
        ]
    return pd.DataFrame(list(measures))


def evidence_drilldown(view: GraphViewModel, element_id: str) -> dict[str, Any]:
    """Resolve a graph selection to evidence/provenance identifiers for close reading."""
    element: ViewNode | ViewEdge | None = next(
        (node for node in view.nodes if node.id == element_id), None
    )
    if element is None:
        element = next((edge for edge in view.edges if edge.id == element_id), None)
    if element is None:
        raise KeyError(element_id)
    return {
        "projection_id": view.projection_id,
        "source_analysis_run": view.source_analysis_run,
        "provenance_id": view.provenance_id,
        "element_id": element.id,
        "review_status": element.review_status,
        "uncertainty": element.uncertainty,
        "evidence": [
            {
                "source_url": link.source_url,
                "evidence_id": link.evidence_id,
                "statement_id": link.statement_id,
                "annotation_id": link.annotation_id,
                "external_ids": dict(link.external_ids),
            }
            for link in element.evidence
        ],
        "safeguards": list(view.safeguards),
    }


def _aggregate_review_state(states: set[str]) -> str:
    states.discard("")
    if not states:
        return "UNREVIEWED"
    if "PROVISIONAL" in states:
        return "PROVISIONAL"
    if len(states) == 1:
        return next(iter(states))
    return "MIXED"


def _evidence_links(values: Iterable[Mapping[str, Any]]) -> tuple[EvidenceLink, ...]:
    links: list[EvidenceLink] = []
    for item in values:
        links.append(
            EvidenceLink(
                source_url=str(item.get("source_url") or ""),
                evidence_id=item.get("evidence_id"),
                statement_id=item.get("statement_id"),
                annotation_id=item.get("annotation_id"),
                external_ids={str(k): str(v) for k, v in (item.get("external_ids") or {}).items()},
            )
        )
    return tuple(links)


def _node_from_mapping(item: Mapping[str, Any]) -> ViewNode:
    return ViewNode(
        id=str(item.get("id") or item.get("key")),
        label=str(item.get("label") or item.get("id") or item.get("key")),
        node_type=str(item.get("node_type") or item.get("type") or "node"),
        external_ids={str(k): str(v) for k, v in (item.get("external_ids") or {}).items()},
        attributes=dict(item.get("attributes") or {}),
        review_status=item.get("review_status"),
        uncertainty=item.get("uncertainty"),
        evidence=_evidence_links(item.get("evidence") or ()),
    )


def _edge_from_mapping(item: Mapping[str, Any]) -> ViewEdge:
    return ViewEdge(
        id=str(item.get("id") or f"{item.get('source')}->{item.get('target')}"),
        source=str(item.get("source")),
        target=str(item.get("target")),
        edge_type=str(item.get("edge_type") or item.get("type") or "relation"),
        weight=float(item.get("weight", 1.0)),
        directed=bool(item.get("directed", False)),
        attributes=dict(item.get("attributes") or {}),
        review_status=item.get("review_status"),
        uncertainty=item.get("uncertainty"),
        evidence=_evidence_links(item.get("evidence") or ()),
    )
