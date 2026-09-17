"""Backend-independent research queries for records, bounded graphs and optional retrieval.

The UI consumes :class:`DataProduct` objects from this module. MongoDB-specific query code
stays here so Streamlit components can run unchanged against CSV/local data or a future graph
backend. MongoDB is a preferred shared remote store, not a second scientific ontology.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import pandas as pd

from .config import Settings
from .data import filter_frame, frame_from_records, normalize_frame
from .products import DataProduct, EvidenceRef, ProductKind


class BackendUnavailable(RuntimeError):
    """Raised when an explicitly requested research backend cannot be used."""


@dataclass(frozen=True, slots=True)
class GraphRequest:
    """A bounded graph request shared by local and remote providers."""

    roots: tuple[str, ...] = ()
    dataset: str | None = None
    country: str | None = None
    arena: str | None = None
    platform: str | None = None
    actor: str | None = None
    signifier: str | None = None
    frame: str | None = None
    start: datetime | str | None = None
    end: datetime | str | None = None
    depth: int = 1
    max_nodes: int = 250
    max_edges: int = 500

    def bounded(self, settings: Settings) -> "GraphRequest":
        return GraphRequest(
            roots=tuple(self.roots[:50]),
            dataset=self.dataset,
            country=self.country,
            arena=self.arena,
            platform=self.platform,
            actor=self.actor,
            signifier=self.signifier,
            frame=self.frame,
            start=self.start,
            end=self.end,
            depth=max(1, min(int(self.depth), settings.graph_max_depth)),
            max_nodes=max(1, min(int(self.max_nodes), settings.graph_max_nodes)),
            max_edges=max(1, min(int(self.max_edges), settings.graph_max_edges)),
        )


@dataclass(frozen=True, slots=True)
class VectorCapability:
    available: bool
    backend: str
    index_name: str | None = None
    embedding_path: str | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ContextRequest:
    source_url: str
    limit: int = 10
    num_candidates: int = 100


class ResearchQueryBackend(Protocol):
    """Storage-neutral query contract used by the visualization workbench."""

    name: str

    def records(self, *, limit: int | None = None) -> DataProduct: ...

    def graph(self, request: GraphRequest) -> DataProduct: ...

    def vector_capability(self) -> VectorCapability: ...

    def context(self, request: ContextRequest) -> DataProduct: ...


@dataclass(slots=True)
class CsvQueryBackend:
    """Portable local provider built from the normalized researcher dataframe."""

    frame: pd.DataFrame
    project_id: str = "default"
    name: str = "csv"

    def __post_init__(self) -> None:
        self.frame = normalize_frame(self.frame)

    def records(self, *, limit: int | None = None) -> DataProduct:
        frame = self.frame if limit is None else self.frame.head(max(0, int(limit)))
        return DataProduct(
            ProductKind.RECORDS,
            frame.copy(),
            project=self.project_id,
            metadata={"backend": self.name, "vector_search": False},
        )

    def graph(self, request: GraphRequest) -> DataProduct:
        frame = _filter_graph_frame(self.frame, request)
        payload, evidence = graph_from_frame(frame, request)
        return DataProduct(
            ProductKind.KNOWLEDGE_GRAPH,
            payload,
            project=self.project_id,
            metadata={
                "backend": self.name,
                "bounded": True,
                "depth": request.depth,
                "max_nodes": request.max_nodes,
                "max_edges": request.max_edges,
                "vector_search": False,
            },
            evidence=evidence,
        )

    def vector_capability(self) -> VectorCapability:
        return VectorCapability(
            False,
            backend=self.name,
            reason="MongoDB vector search is not available in CSV/local mode.",
        )

    def context(self, request: ContextRequest) -> DataProduct:
        del request
        return DataProduct(
            ProductKind.RETRIEVAL,
            [],
            project=self.project_id,
            metadata={
                "backend": self.name,
                "available": False,
                "reason": "Vector retrieval is unavailable in CSV/local mode.",
            },
        )


def _filter_graph_frame(frame: pd.DataFrame, request: GraphRequest) -> pd.DataFrame:
    result = filter_frame(
        frame,
        platforms=[request.platform] if request.platform else None,
        countries=[request.country] if request.country else None,
        authors=[request.actor] if request.actor else None,
        start=request.start,
        end=request.end,
    )
    scalar = {
        "dataset": request.dataset,
        "arena": request.arena,
    }
    for column, value in scalar.items():
        if value and column in result:
            result = result[result[column].astype(str) == value]
    list_filters = {
        "signifiers": request.signifier,
        "frames": request.frame,
    }
    for column, value in list_filters.items():
        if value and column in result:
            result = result[result[column].map(lambda items: value in {str(item) for item in items})]
    return result


def _value_id(kind: str, value: Any) -> str:
    return f"{kind}:{str(value).strip()}"


def _record_id(row: Mapping[str, Any]) -> str:
    return str(row.get("source_url") or row.get("document_id") or "").strip()


def _relation_state(relation: Mapping[str, Any]) -> str:
    if relation.get("human_validated") is True or relation.get("validated") is True:
        return "human_validated"
    return str(relation.get("provenance_type") or relation.get("origin") or "extracted_or_inferred")


def graph_from_frame(
    frame: pd.DataFrame,
    request: GraphRequest,
) -> tuple[dict[str, Any], tuple[EvidenceRef, ...]]:
    """Build a bounded shared-schema graph from portable record relationship fields."""
    max_nodes = max(1, int(request.max_nodes))
    max_edges = max(1, int(request.max_edges))
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    evidence: dict[tuple[str, str | None], EvidenceRef] = {}

    def add_node(node_id: str, kind: str, label: str, source_url: str | None = None) -> bool:
        if not node_id:
            return False
        if node_id not in nodes and len(nodes) >= max_nodes:
            return False
        nodes.setdefault(
            node_id,
            {"id": node_id, "type": kind, "label": label, "source_url": source_url or ""},
        )
        return True

    def add_edge(edge: dict[str, Any]) -> None:
        if len(edges) >= max_edges:
            return
        if edge["source"] in nodes and edge["target"] in nodes:
            edges.append(edge)

    rows = frame.to_dict(orient="records")
    root_filter = set(request.roots)
    if root_filter:
        rows = [row for row in rows if _record_id(row) in root_filter]

    implicit_fields = (
        ("source_author", "Actor", "mentions_actor"),
        ("source_platform", "Platform", "published_on"),
        ("source_country", "Location", "located_in"),
        ("dataset", "Dataset", "belongs_to_dataset"),
        ("arena", "Arena", "belongs_to_arena"),
    )
    list_fields = (
        ("signifiers", "Signifier", "articulates_signifier"),
        ("frames", "Frame", "uses_frame"),
        ("imaginaries", "Imaginary", "articulates_imaginary"),
        ("topics", "Topic", "has_topic"),
        ("entities", "Actor", "mentions_entity"),
    )

    for row in rows:
        source_url = _record_id(row)
        if not source_url:
            continue
        record_node = f"Record:{source_url}"
        label = str(row.get("summary") or source_url)[:180]
        if not add_node(record_node, "Record", label, source_url):
            break
        evidence[(source_url, None)] = EvidenceRef(record_id=source_url, source_url=source_url)

        for field_name, kind, relation_type in implicit_fields:
            value = row.get(field_name)
            if value in (None, ""):
                continue
            target = _value_id(kind, value)
            if add_node(target, kind, str(value)):
                add_edge(
                    {
                        "source": record_node,
                        "target": target,
                        "type": relation_type,
                        "source_url": source_url,
                        "provenance": "record_field",
                        "validation_status": str(row.get("review_status") or "PROVISIONAL"),
                    }
                )

        for field_name, kind, relation_type in list_fields:
            values = row.get(field_name, [])
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, Mapping):
                    label_value = value.get("label") or value.get("name") or value.get("id")
                else:
                    label_value = value
                if label_value in (None, ""):
                    continue
                target = _value_id(kind, label_value)
                if add_node(target, kind, str(label_value)):
                    add_edge(
                        {
                            "source": record_node,
                            "target": target,
                            "type": relation_type,
                            "source_url": source_url,
                            "provenance": "record_field",
                            "validation_status": str(row.get("review_status") or "PROVISIONAL"),
                        }
                    )

        relations = row.get("relations", [])
        if not isinstance(relations, list):
            continue
        for relation in relations:
            if not isinstance(relation, Mapping):
                continue
            raw_source = relation.get("source_ref") or relation.get("source")
            raw_target = relation.get("target_ref") or relation.get("target")
            if raw_source in (None, "") or raw_target in (None, ""):
                continue
            source = str(raw_source)
            target = str(raw_target)
            source_kind = str(relation.get("source_type") or "Entity")
            target_kind = str(relation.get("target_type") or "Entity")
            source_id = source if ":" in source else _value_id(source_kind, source)
            target_id = target if ":" in target else _value_id(target_kind, target)
            if not add_node(source_id, source_kind, source):
                continue
            if not add_node(target_id, target_kind, target):
                continue
            add_edge(
                {
                    "source": source_id,
                    "target": target_id,
                    "type": str(relation.get("relation_type") or relation.get("type") or "related"),
                    "source_url": source_url,
                    "provenance": str(
                        relation.get("evidence")
                        or relation.get("provenance")
                        or relation.get("evidence_ref")
                        or "relation_field"
                    ),
                    "validation_status": _relation_state(relation),
                }
            )

    payload = {
        "nodes": list(nodes.values()),
        "edges": edges,
        "bounded": True,
        "truncated": len(nodes) >= max_nodes or len(edges) >= max_edges,
        "limits": {"nodes": max_nodes, "edges": max_edges, "depth": request.depth},
    }
    return payload, tuple(evidence.values())


@dataclass(slots=True)
class MongoQueryBackend:
    """MongoDB implementation with lazy client injection and bounded queries."""

    settings: Settings
    client: Any
    name: str = "mongodb"
    _vector_capability: VectorCapability | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_settings(cls, settings: Settings) -> "MongoQueryBackend":
        if not settings.mongodb_uri:
            raise BackendUnavailable("MongoDB is not configured. Set LACLAUGPT_VIS_MONGODB_URI.")
        try:
            from pymongo import MongoClient
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise BackendUnavailable(
                "MongoDB mode requires laclaugpt-data-visualization[remote]."
            ) from exc
        client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=settings.mongodb_connect_timeout_ms,
            connectTimeoutMS=settings.mongodb_connect_timeout_ms,
            appname="laclaugpt-data-visualization",
        )
        backend = cls(settings=settings, client=client)
        backend.probe()
        return backend

    @property
    def database(self):
        return self.client[self.settings.mongodb_database]

    @property
    def collection(self):
        return self.database[self.settings.resolved_mongodb_collection]

    @property
    def graph_collection(self):
        return self.database[self.settings.resolved_mongodb_graph_collection]

    def probe(self) -> None:
        try:
            self.client.admin.command("ping")
        except _mongo_exception_types() as exc:
            raise BackendUnavailable("Configured MongoDB is unavailable.") from exc

    def records(self, *, limit: int | None = None) -> DataProduct:
        query = {"project_id": self.settings.project_id}
        cursor = self.collection.find(query, {"_id": False})
        if limit is not None and hasattr(cursor, "limit"):
            cursor = cursor.limit(max(0, int(limit)))
        frame = frame_from_records(list(cursor))
        return DataProduct(
            ProductKind.RECORDS,
            frame,
            project=self.settings.project_id,
            metadata={"backend": self.name, "vector_search": self.vector_capability().available},
        )

    def graph(self, request: GraphRequest) -> DataProduct:
        bounded = request.bounded(self.settings)
        records = self._graph_records(bounded)
        frame = frame_from_records(records)
        payload, evidence = graph_from_frame(frame, bounded)
        payload["backend"] = self.name
        payload["query_filters"] = _safe_graph_filters(bounded)
        return DataProduct(
            ProductKind.KNOWLEDGE_GRAPH,
            payload,
            project=self.settings.project_id,
            metadata={
                "backend": self.name,
                "bounded": True,
                "depth": bounded.depth,
                "max_nodes": bounded.max_nodes,
                "max_edges": bounded.max_edges,
            },
            evidence=evidence,
        )

    def _graph_records(self, request: GraphRequest) -> list[dict[str, Any]]:
        match: dict[str, Any] = {"project_id": self.settings.project_id}
        filters = {
            "dataset": request.dataset,
            "source_country": request.country,
            "arena": request.arena,
            "source_platform": request.platform,
            "source_author": request.actor,
        }
        for key, value in filters.items():
            if value:
                match[key] = value
        if request.signifier:
            match["signifiers"] = request.signifier
        if request.frame:
            match["frames"] = request.frame
        if request.start or request.end:
            time_filter: dict[str, Any] = {}
            if request.start:
                time_filter["$gte"] = request.start
            if request.end:
                time_filter["$lte"] = request.end
            match["source_timestamp"] = time_filter
        if request.roots:
            match["source_url"] = {"$in": list(request.roots)}
        # Record count is deliberately coupled to graph limits so one browser request
        # cannot materialize the complete corpus graph.
        record_limit = max(1, min(request.max_nodes, self.settings.graph_max_nodes))
        cursor = self.collection.find(match, {"_id": False})
        if hasattr(cursor, "limit"):
            cursor = cursor.limit(record_limit)
        return list(cursor)[:record_limit]

    def graph_lookup(self, roots: Iterable[str], *, depth: int = 1, limit: int = 250) -> list[dict[str, Any]]:
        """Optional bounded traversal for deployments with a canonical relation collection.

        The relation collection is expected to use shared ``source_ref``/``target_ref`` fields.
        Embedded per-record relationships remain the portable baseline.
        """
        clean_roots = [str(value) for value in roots if str(value)][:50]
        if not clean_roots:
            return []
        max_depth = max(0, min(int(depth) - 1, self.settings.graph_max_depth - 1))
        result_limit = max(1, min(int(limit), self.settings.graph_max_edges))
        pipeline = [
            {"$match": {"project_id": self.settings.project_id, "source_ref": {"$in": clean_roots}}},
            {"$limit": result_limit},
            {
                "$graphLookup": {
                    "from": self.settings.resolved_mongodb_graph_collection,
                    "startWith": "$target_ref",
                    "connectFromField": "target_ref",
                    "connectToField": "source_ref",
                    "as": "neighbours",
                    "maxDepth": max_depth,
                    "restrictSearchWithMatch": {"project_id": self.settings.project_id},
                }
            },
            {"$project": {"_id": 0, "neighbours": {"$slice": ["$neighbours", result_limit]}}},
            {"$limit": result_limit},
        ]
        try:
            return list(self.graph_collection.aggregate(pipeline, maxTimeMS=3000))[:result_limit]
        except _mongo_exception_types():
            return []

    def vector_capability(self) -> VectorCapability:
        if self._vector_capability is not None:
            return self._vector_capability
        try:
            if not hasattr(self.collection, "list_search_indexes"):
                raise AttributeError("list_search_indexes unavailable")
            indexes = list(self.collection.list_search_indexes())
            for index in indexes:
                name = str(index.get("name") or "") if isinstance(index, Mapping) else ""
                if name == self.settings.mongodb_vector_index:
                    self._vector_capability = VectorCapability(
                        True,
                        backend=self.name,
                        index_name=name,
                        embedding_path=self.settings.mongodb_embedding_path,
                    )
                    return self._vector_capability
            self._vector_capability = VectorCapability(
                False,
                backend=self.name,
                index_name=self.settings.mongodb_vector_index,
                embedding_path=self.settings.mongodb_embedding_path,
                reason="Configured MongoDB vector search index was not found.",
            )
        except (*_mongo_exception_types(), AttributeError, TypeError, ValueError):
            self._vector_capability = VectorCapability(
                False,
                backend=self.name,
                index_name=self.settings.mongodb_vector_index,
                embedding_path=self.settings.mongodb_embedding_path,
                reason="MongoDB vector search capability could not be confirmed.",
            )
        return self._vector_capability

    def context(self, request: ContextRequest) -> DataProduct:
        capability = self.vector_capability()
        limit = max(1, min(int(request.limit), self.settings.vector_max_results))
        if not capability.available:
            return DataProduct(
                ProductKind.RETRIEVAL,
                [],
                project=self.settings.project_id,
                metadata={
                    "backend": self.name,
                    "available": False,
                    "reason": capability.reason,
                    "index_name": capability.index_name,
                },
            )
        source = self.collection.find_one(
            {"project_id": self.settings.project_id, "source_url": request.source_url},
            {"_id": False, self.settings.mongodb_embedding_path: True},
        )
        vector = _nested_get(source or {}, self.settings.mongodb_embedding_path)
        if not isinstance(vector, list) or not vector:
            return DataProduct(
                ProductKind.RETRIEVAL,
                [],
                project=self.settings.project_id,
                metadata={
                    "backend": self.name,
                    "available": False,
                    "reason": "Selected record has no usable embedding vector.",
                    "index_name": capability.index_name,
                },
            )
        num_candidates = max(limit, min(int(request.num_candidates), 10000))
        pipeline = [
            {
                "$vectorSearch": {
                    "index": self.settings.mongodb_vector_index,
                    "path": self.settings.mongodb_embedding_path,
                    "queryVector": vector,
                    "numCandidates": num_candidates,
                    "limit": limit + 1,
                    "filter": {"project_id": self.settings.project_id},
                }
            },
            {"$match": {"source_url": {"$ne": request.source_url}}},
            {
                "$project": {
                    "_id": 0,
                    "source_url": 1,
                    "summary": 1,
                    "source_author": 1,
                    "source_platform": 1,
                    "dataset": 1,
                    "arena": 1,
                    "score": {"$meta": "vectorSearchScore"},
                    "embedding_model": 1,
                    "embedding_version": 1,
                }
            },
            {"$limit": limit},
        ]
        try:
            rows = list(self.collection.aggregate(pipeline, maxTimeMS=5000))[:limit]
        except _mongo_exception_types() as exc:
            raise BackendUnavailable("MongoDB vector retrieval failed.") from exc
        evidence = tuple(
            EvidenceRef(record_id=str(row.get("source_url") or ""), source_url=row.get("source_url"))
            for row in rows
            if row.get("source_url")
        )
        return DataProduct(
            ProductKind.RETRIEVAL,
            rows,
            project=self.settings.project_id,
            metadata={
                "backend": self.name,
                "available": True,
                "index_name": capability.index_name,
                "embedding_path": capability.embedding_path,
                "source_url": request.source_url,
                "limit": limit,
                "num_candidates": num_candidates,
            },
            evidence=evidence,
        )


def _mongo_exception_types() -> tuple[type[BaseException], ...]:
    try:
        from pymongo.errors import PyMongoError
    except ImportError:  # pragma: no cover - optional dependency
        return (ConnectionError, TimeoutError)
    return (PyMongoError, ConnectionError, TimeoutError)


def _nested_get(document: Mapping[str, Any], path: str) -> Any:
    value: Any = document
    for part in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _safe_graph_filters(request: GraphRequest) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "dataset": request.dataset,
            "country": request.country,
            "arena": request.arena,
            "platform": request.platform,
            "actor": request.actor,
            "signifier": request.signifier,
            "frame": request.frame,
            "start": str(request.start) if request.start else None,
            "end": str(request.end) if request.end else None,
        }.items()
        if value not in (None, "")
    }


def resolve_query_backend(
    settings: Settings,
    local_frame: pd.DataFrame,
    *,
    mongo_backend_factory: Any | None = None,
) -> ResearchQueryBackend:
    """Resolve ``auto | mongodb | csv`` without making local mode MongoDB-dependent."""
    mode = settings.storage_backend
    if mode == "csv":
        return CsvQueryBackend(local_frame, project_id=settings.project_id)
    factory = mongo_backend_factory or MongoQueryBackend.from_settings
    if mode == "mongodb":
        if not settings.mongodb_uri:
            raise BackendUnavailable("MongoDB mode requires LACLAUGPT_VIS_MONGODB_URI.")
        return factory(settings)
    if settings.mongodb_uri:
        try:
            return factory(settings)
        except BackendUnavailable:
            pass
    return CsvQueryBackend(local_frame, project_id=settings.project_id)
