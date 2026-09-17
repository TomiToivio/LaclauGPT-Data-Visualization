"""Optional, project-gated RDF/Linked Data support for the dashboard.

The visualization layer deliberately talks to an Analysis-owned service contract rather
than to Fuseki, GraphDB, Stardog, Blazegraph, Virtuoso, Oxigraph, RDFLib, or another
store directly.  This keeps RDF as an optional research lens over canonical evidence.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib import error, request

import yaml

READ_ONLY_SPARQL = frozenset({"SELECT", "CONSTRUCT", "DESCRIBE", "ASK"})
FORBIDDEN_SPARQL = re.compile(
    r"\b(INSERT|DELETE|LOAD|CLEAR|CREATE|DROP|COPY|MOVE|ADD|WITH|USING|SERVICE)\b",
    re.IGNORECASE,
)

DEFAULT_PREFIXES: dict[str, str] = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "prov": "http://www.w3.org/ns/prov#",
    "dcterms": "http://purl.org/dc/terms/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "schema": "https://schema.org/",
    "oa": "http://www.w3.org/ns/oa#",
    "ontolex": "http://www.w3.org/ns/lemon/ontolex#",
    "nif": "http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#",
    "time": "http://www.w3.org/2006/time#",
    "geo": "http://www.opengis.net/ont/geosparql#",
    "aif": "http://www.arg.dundee.ac.uk/aif#",
}

LACLAU_HINTS = {
    "articulation": "Analytical articulation",
    "discourseformation": "Discourse formation",
    "signifier": "Signifier",
    "emptysignifier": "Empty signifier candidate",
    "floatingsignifier": "Floating signifier candidate",
    "nodalpoint": "Nodal point candidate",
    "chainofequivalence": "Chain of equivalence",
    "antagonism": "Antagonism",
    "discursivefrontier": "Discursive frontier",
}

THEORY_CAVEAT = (
    "Graph degree, centrality, community structure, co-occurrence, negative edges and layout "
    "distance are descriptive aids. They do not by themselves establish nodal status, hegemony, "
    "ideological formation, equivalence, antagonistic frontier or theoretical distance."
)


@dataclass(frozen=True, slots=True)
class RDFProjectPolicy:
    enabled: bool = False
    required: bool = False
    graphrag_enabled: bool = False

    @classmethod
    def from_mapping(cls, project: Mapping[str, Any] | None) -> "RDFProjectPolicy":
        if not isinstance(project, Mapping):
            return cls()
        analysis = project.get("analysis")
        if not isinstance(analysis, Mapping):
            return cls()
        rdf = analysis.get("rdf")
        if not isinstance(rdf, Mapping):
            return cls()
        graphrag = rdf.get("graphrag")
        return cls(
            enabled=bool(rdf.get("enabled", False)),
            required=bool(rdf.get("required", False)),
            graphrag_enabled=bool(
                graphrag.get("enabled", False) if isinstance(graphrag, Mapping) else False
            ),
        )


@dataclass(frozen=True, slots=True)
class RDFLimits:
    depth: int = 1
    nodes: int = 200
    edges: int = 400
    rows: int = 500
    timeout_seconds: int = 10

    def __post_init__(self) -> None:
        if not 0 <= self.depth <= 4:
            raise ValueError("RDF depth must be between 0 and 4")
        if not 1 <= self.nodes <= 1000:
            raise ValueError("RDF node limit must be between 1 and 1000")
        if not 1 <= self.edges <= 2500:
            raise ValueError("RDF edge limit must be between 1 and 2500")
        if not 1 <= self.rows <= 5000:
            raise ValueError("RDF row limit must be between 1 and 5000")
        if not 1 <= self.timeout_seconds <= 30:
            raise ValueError("RDF timeout must be between 1 and 30 seconds")

    def as_dict(self) -> dict[str, int]:
        return {
            "depth": self.depth,
            "nodes": self.nodes,
            "edges": self.edges,
            "rows": self.rows,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class RDFSubgraph:
    nodes: tuple[Mapping[str, Any], ...] = ()
    edges: tuple[Mapping[str, Any], ...] = ()
    truncated: bool = False
    query: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], limits: RDFLimits) -> "RDFSubgraph":
        nodes = tuple(payload.get("nodes") or ())
        edges = tuple(payload.get("edges") or ())
        if len(nodes) > limits.nodes or len(edges) > limits.edges:
            raise ValueError("RDF provider returned an unbounded subgraph")
        return cls(
            nodes=nodes,
            edges=edges,
            truncated=bool(payload.get("truncated", False)),
            query=payload.get("query"),
            provenance=payload.get("provenance") or {},
        )


class RDFQueryProvider(Protocol):
    """Small vendor-neutral contract consumed by the visualization layer."""

    def health(self) -> Mapping[str, Any]: ...

    def capabilities(self) -> Mapping[str, Any]: ...

    def query_subgraph(
        self, filters: Mapping[str, Any], limits: RDFLimits
    ) -> RDFSubgraph: ...

    def query_table(
        self, query: str, *, limit: int, timeout_seconds: int
    ) -> Sequence[Mapping[str, Any]]: ...

    def describe_resource(self, uri: str) -> Mapping[str, Any]: ...

    def list_named_graphs(self) -> Sequence[Mapping[str, Any] | str]: ...

    def export(
        self, *, format: str, selection: Mapping[str, Any], limits: RDFLimits
    ) -> Mapping[str, Any]: ...

    def graphrag_context(self, selection: Mapping[str, Any]) -> Mapping[str, Any]: ...


class AnalysisHTTPRDFProvider:
    """Adapter for a stable Analysis-owned HTTP API, not for a database vendor API."""

    def __init__(self, base_url: str, *, project_id: str, timeout_seconds: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id
        self.timeout_seconds = timeout_seconds

    def _request(
        self, path: str, payload: Mapping[str, Any] | None = None, *, method: str = "POST"
    ) -> Any:
        url = f"{self.base_url}{path}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except (error.URLError, TimeoutError, OSError) as exc:
            raise ConnectionError(f"RDF Analysis service unavailable: {exc}") from exc
        return json.loads(raw) if raw else {}

    def health(self) -> Mapping[str, Any]:
        return self._request("/health", method="GET")

    def capabilities(self) -> Mapping[str, Any]:
        return self._request(
            f"/rdf/capabilities?project={self.project_id}", method="GET"
        )

    def query_subgraph(self, filters: Mapping[str, Any], limits: RDFLimits) -> RDFSubgraph:
        payload = self._request(
            "/rdf/subgraph",
            {"project_id": self.project_id, "filters": dict(filters), "limits": limits.as_dict()},
        )
        return RDFSubgraph.from_payload(payload, limits)

    def query_table(
        self, query: str, *, limit: int, timeout_seconds: int
    ) -> Sequence[Mapping[str, Any]]:
        validate_read_only_sparql(query)
        payload = self._request(
            "/rdf/query",
            {
                "project_id": self.project_id,
                "query": query,
                "limit": min(max(1, limit), 5000),
                "timeout_seconds": min(max(1, timeout_seconds), 30),
                "read_only": True,
            },
        )
        return tuple(payload.get("rows") or ())

    def describe_resource(self, uri: str) -> Mapping[str, Any]:
        return self._request("/rdf/describe", {"project_id": self.project_id, "uri": uri})

    def list_named_graphs(self) -> Sequence[Mapping[str, Any] | str]:
        payload = self._request(f"/rdf/graphs?project={self.project_id}", method="GET")
        return tuple(payload.get("graphs") or ())

    def export(
        self, *, format: str, selection: Mapping[str, Any], limits: RDFLimits
    ) -> Mapping[str, Any]:
        if format not in {"json-ld", "turtle", "n-quads", "n-triples", "trig", "rdf-xml"}:
            raise ValueError("unsupported RDF export format")
        return self._request(
            "/rdf/export",
            {
                "project_id": self.project_id,
                "format": format,
                "selection": dict(selection),
                "limits": limits.as_dict(),
            },
        )

    def graphrag_context(self, selection: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._request(
            "/rdf/graphrag/context",
            {"project_id": self.project_id, "selection": dict(selection)},
        )


def validate_read_only_sparql(query: str) -> str:
    cleaned = re.sub(r"(?m)^\s*(PREFIX|BASE)\b.*$", "", query).strip()
    if not cleaned:
        raise ValueError("SPARQL query is empty")
    if FORBIDDEN_SPARQL.search(cleaned):
        raise ValueError("SPARQL update/federation operations are not allowed in the dashboard")
    match = re.search(r"\b(SELECT|CONSTRUCT|DESCRIBE|ASK)\b", cleaned, re.IGNORECASE)
    if not match or match.group(1).upper() not in READ_ONLY_SPARQL:
        raise ValueError("dashboard SPARQL must be SELECT, CONSTRUCT, DESCRIBE or ASK")
    return query


def compact_uri(uri: str, prefixes: Mapping[str, str] | None = None) -> str:
    namespaces = {**DEFAULT_PREFIXES, **dict(prefixes or {})}
    for prefix, base in sorted(namespaces.items(), key=lambda item: len(item[1]), reverse=True):
        if uri.startswith(base):
            return f"{prefix}:{uri[len(base):]}"
    return uri


def preferred_label(
    resource: Mapping[str, Any], languages: Sequence[str] = ("en", "fi", "pl")
) -> str:
    labels = resource.get("labels") or resource.get("label") or {}
    if isinstance(labels, str):
        return labels
    if isinstance(labels, Mapping):
        for language in languages:
            value = labels.get(language)
            if value:
                return str(value)
        for value in labels.values():
            if value:
                return str(value)
    uri = str(resource.get("uri") or resource.get("id") or "")
    return compact_uri(uri) if uri else "(unlabelled resource)"


def theory_label(resource: Mapping[str, Any]) -> str | None:
    values = resource.get("types") or resource.get("type") or ()
    if isinstance(values, str):
        values = (values,)
    for value in values:
        token = re.sub(r"[^a-z]", "", compact_uri(str(value)).split(":")[-1].lower())
        if token in LACLAU_HINTS:
            return LACLAU_HINTS[token]
    return None


def evidence_path(resource: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize drill-down identifiers without creating another review/evidence store."""
    provenance = resource.get("provenance") or {}
    evidence = resource.get("evidence") or {}
    return {
        "rdf_resource": resource.get("uri") or resource.get("id"),
        "analytical_object": resource.get("analytical_object_id") or resource.get("object_id"),
        "evidence": evidence,
        "source_record": resource.get("source_record_id") or resource.get("source_url"),
        "analysis_run": provenance.get("run_id") or resource.get("run_id"),
        "model": provenance.get("model") or resource.get("model"),
        "plugin": provenance.get("plugin") or resource.get("plugin"),
        "prompt": provenance.get("prompt_id") or resource.get("prompt_id"),
        "codebook": provenance.get("codebook_id") or resource.get("codebook_id"),
        "review_status": resource.get("review_status") or provenance.get("review_status"),
    }


def load_project_policy(data_dir: Path, project_id: str) -> RDFProjectPolicy:
    """Read project policy only; runtime endpoint settings can never turn RDF on."""
    candidates = (
        data_dir / "config" / f"{project_id}.yaml",
        data_dir / "config" / f"{project_id}.yml",
        data_dir / "config" / "project.yaml",
        data_dir / "config" / "project.yml",
    )
    for path in candidates:
        if not path.exists():
            continue
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return RDFProjectPolicy.from_mapping(payload)
    return RDFProjectPolicy()


def configured_provider(project_id: str) -> AnalysisHTTPRDFProvider | None:
    """Return a provider only when runtime endpoint details exist.

    This does not make RDF enabled. Callers must first enforce ``RDFProjectPolicy.enabled``.
    """
    service_url = os.getenv("LACLAUGPT_VIS_RDF_SERVICE_URL", "").strip()
    if not service_url:
        return None
    return AnalysisHTTPRDFProvider(service_url, project_id=project_id)
