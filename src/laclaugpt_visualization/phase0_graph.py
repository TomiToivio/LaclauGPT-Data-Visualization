"""Isolated Phase 0 discourse-graph compatibility adapter.

This module renders only the graph information already present in the Phase 0
ontology export. It does not infer new relations, promote candidate discourse
objects, or rewrite Phase 0 data into the canonical Phase 1 graph contract.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

_CANDIDATE_TYPES = {
    "lg:NodalPoint": "nodal-point-candidate",
    "lg:FloatingSignifier": "floating-signifier-candidate",
    "lg:EmptySignifier": "empty-signifier-candidate",
}

_TYPE_LABELS = {
    "lg:Document": "document",
    "lg:AnalysisRun": "analysis-run",
    "lg:Signifier": "signifier",
    "lg:Actor": "actor",
    "lg:Affect": "affect",
    "lg:Frontier": "frontier-candidate",
    "lg:AnalysisAssertion": "analysis-assertion",
    **_CANDIDATE_TYPES,
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _id_ref(value: Any) -> str:
    if isinstance(value, Mapping):
        return _string(value.get("@id"))
    return _string(value)


def _ontology_from_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
    compatibility = _mapping(record.get("phase0_compatibility"))
    raw_phase0 = _mapping(compatibility.get("raw_phase0"))
    ontology = raw_phase0.get("phase0_ontology")
    if ontology is None:
        ontology = record.get("phase0_ontology")
    ontology_map = _mapping(ontology)
    return _mapping(ontology_map.get("jsonld") or ontology_map)


def phase0_graph_projection(
    record: Mapping[str, Any],
    *,
    max_nodes: int = 200,
    max_edges: int = 200,
) -> dict[str, Any]:
    """Return a bounded, explicitly provisional graph from one Phase 0 record.

    The adapter consumes the Phase 0 JSON-LD export only. It never derives graph
    relations from label co-occurrence and never upgrades candidate discourse
    semantics into validated claims.
    """
    node_limit = max(1, int(max_nodes))
    edge_limit = max(1, int(max_edges))
    ontology = _ontology_from_record(record)
    graph = ontology.get("@graph")
    if not isinstance(graph, list):
        graph = []

    source_url = _string(record.get("source_url"))
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    raw_node_count = 0
    raw_edge_count = 0

    for item in graph:
        if not isinstance(item, Mapping):
            continue
        rdf_type = _string(item.get("@type"))
        if rdf_type == "lg:AnalysisAssertion":
            raw_edge_count += 1
            if len(edges) >= edge_limit:
                continue
            source = _id_ref(item.get("lg:subject"))
            target = _id_ref(item.get("lg:object"))
            relation = _id_ref(item.get("lg:relation"))
            if not source or not target:
                continue
            edge = {
                "source": source,
                "target": target,
                "type": relation or "phase0:related",
                "source_url": source_url,
                "evidence_refs": [],
                "evidence_text": _string(item.get("lg:surfaceForm")),
                "phase0_semantics": "candidate/provisional",
                "validated_flag_from_phase0": bool(item.get("lg:validated", False)),
                "origin": "phase0_ontology",
            }
            edges.append(edge)
            continue

        resource_id = _string(item.get("@id"))
        if not resource_id:
            continue
        raw_node_count += 1
        if len(nodes) >= node_limit or resource_id in node_ids:
            continue
        node_ids.add(resource_id)
        kind = _TYPE_LABELS.get(rdf_type, rdf_type or "resource")
        node = {
            "id": resource_id,
            "label": _string(item.get("skos:prefLabel")) or resource_id,
            "kinds": [kind],
            "source_url": source_url,
            "evidence_text": _string(item.get("lg:surfaceForm")),
            "phase0_semantics": (
                "candidate/provisional"
                if rdf_type in _CANDIDATE_TYPES
                else "phase0-export"
            ),
            "origin": "phase0_ontology",
        }
        nodes.append(node)

    visible_ids = {node["id"] for node in nodes}
    filtered_edges = [
        edge
        for edge in edges
        if edge["source"] in visible_ids and edge["target"] in visible_ids
    ]

    return {
        "nodes": deepcopy(nodes),
        "edges": deepcopy(filtered_edges[:edge_limit]),
        "bounded": True,
        "truncated": raw_node_count > node_limit or raw_edge_count > edge_limit,
        "limits": {"nodes": node_limit, "edges": edge_limit},
        "source_url": source_url,
        "graph_semantics": "phase0-candidate/provisional",
        "adapter": "phase0-discourse-graph-v1",
        "canonical_phase1_graph": False,
        "interpretation_warning": (
            "Phase 0 discourse graph: candidate/provisional analytical output only. "
            "Graph layout, degree, relation presence, and ontology class labels do not "
            "establish theoretical validity or human validation."
        ),
    }
