from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.query_backends import (
    BackendUnavailable,
    ContextRequest,
    CsvQueryBackend,
    GraphRequest,
    MongoQueryBackend,
    resolve_query_backend,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "project_id": "ai26",
                "source_url": "https://example.invalid/1",
                "summary": "One",
                "source_author": "alice",
                "source_platform": "x",
                "source_country": "FI",
                "dataset": "synthetic",
                "arena": "elites",
                "signifiers": ["AGI"],
                "frames": ["progress"],
                "imaginaries": ["acceleration"],
                "topics": ["compute"],
                "relations": [
                    {
                        "source": "alice",
                        "target": "AGI",
                        "source_type": "Actor",
                        "target_type": "Signifier",
                        "type": "articulates",
                        "human_validated": True,
                        "evidence": "synthetic relation",
                    }
                ],
                "review_status": "ACCEPTED",
            },
            {
                "project_id": "ai26",
                "source_url": "https://example.invalid/2",
                "summary": "Two",
                "source_author": "bob",
                "source_platform": "rss",
                "source_country": "US",
                "dataset": "synthetic",
                "arena": "grassroots",
                "signifiers": ["safety"],
                "frames": ["risk"],
                "relations": [],
            },
        ]
    )


def _settings(tmp_path: Path, **changes) -> Settings:
    values = {
        "project_id": "ai26",
        "data_dir": tmp_path / "data",
        "output_dir": tmp_path / "out",
        "sqlite_path": tmp_path / "data" / "db.sqlite3",
        "storage_backend": "csv",
    }
    values.update(changes)
    return Settings(**values)


def test_csv_graph_is_bounded_and_preserves_provenance(tmp_path: Path) -> None:
    backend = CsvQueryBackend(_frame(), project_id="ai26")
    product = backend.graph(GraphRequest(max_nodes=4, max_edges=4))
    assert product.metadata["bounded"] is True
    assert len(product.payload["nodes"]) <= 4
    assert len(product.payload["edges"]) <= 4
    assert any(
        edge["source_url"] == "https://example.invalid/1"
        for edge in product.payload["edges"]
    )
    assert any(
        edge["validation_status"] == "human_validated"
        for edge in product.payload["edges"]
    )
    assert backend.vector_capability().available is False
    context = backend.context(ContextRequest("https://example.invalid/1"))
    assert context.metadata["available"] is False


def test_auto_falls_back_and_explicit_mongodb_does_not(tmp_path: Path) -> None:
    auto = _settings(
        tmp_path,
        storage_backend="auto",
        mongodb_uri="mongodb://example.invalid:27017",
    )

    def unavailable(_settings):
        raise BackendUnavailable("offline")

    resolved = resolve_query_backend(auto, _frame(), mongo_backend_factory=unavailable)
    assert isinstance(resolved, CsvQueryBackend)

    explicit = _settings(
        tmp_path,
        storage_backend="mongodb",
        mongodb_uri="mongodb://example.invalid:27017",
    )
    with pytest.raises(BackendUnavailable, match="offline"):
        resolve_query_backend(explicit, _frame(), mongo_backend_factory=unavailable)


def test_storage_backend_policy_maps_onto_legacy_loader(tmp_path: Path) -> None:
    auto = _settings(
        tmp_path,
        storage_backend="auto",
        mongodb_uri="mongodb://example.invalid:27017",
    )
    assert auto.data_backend == "mongodb"
    local = _settings(
        tmp_path,
        storage_backend="csv",
        data_backend="mongodb",
        mongodb_uri="mongodb://example.invalid:27017",
    )
    assert local.data_backend == "files"


class FakeCursor(list):
    def limit(self, value: int):
        return FakeCursor(self[:value])


class FakeCollection:
    def __init__(self, records, *, vector: bool = True):
        self.records = list(records)
        self.vector = vector
        self.last_pipeline = None

    def find(self, query, projection=None):
        del projection
        records = self.records
        if query.get("project_id"):
            records = [
                row for row in records if row.get("project_id") == query["project_id"]
            ]
        if query.get("source_url") and isinstance(query["source_url"], dict):
            allowed = set(query["source_url"].get("$in", []))
            records = [row for row in records if row.get("source_url") in allowed]
        return FakeCursor(records)

    def find_one(self, query, projection=None):
        del projection
        for row in self.records:
            if (
                row.get("project_id") == query.get("project_id")
                and row.get("source_url") == query.get("source_url")
            ):
                return row
        return None

    def list_search_indexes(self):
        return [{"name": "laclaugpt_vector", "type": "vectorSearch"}] if self.vector else []

    def aggregate(self, pipeline, maxTimeMS=None):
        del maxTimeMS
        self.last_pipeline = pipeline
        return [
            {
                "source_url": "https://example.invalid/2",
                "summary": "Two",
                "score": 0.91,
                "embedding_model": "synthetic-model",
                "embedding_version": "v1",
            }
        ]


class FakeDatabase:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        del name
        return self.collection


class FakeAdmin:
    def command(self, name):
        assert name == "ping"
        return {"ok": 1}


class FakeClient:
    def __init__(self, collection):
        self.collection = collection
        self.admin = FakeAdmin()

    def __getitem__(self, name):
        del name
        return FakeDatabase(self.collection)


@pytest.fixture
def mongo_backend(tmp_path: Path) -> MongoQueryBackend:
    records = _frame().to_dict(orient="records")
    records[0]["embedding"] = [0.1, 0.2, 0.3]
    settings = _settings(
        tmp_path,
        storage_backend="mongodb",
        mongodb_uri="mongodb://synthetic.invalid:27017",
        graph_max_nodes=8,
        graph_max_edges=12,
    )
    return MongoQueryBackend(settings=settings, client=FakeClient(FakeCollection(records)))


def test_mongodb_graph_and_vector_context_are_backend_neutral(
    mongo_backend: MongoQueryBackend,
) -> None:
    mongo_backend.probe()
    records = mongo_backend.records().payload
    assert set(records["source_url"]) == {
        "https://example.invalid/1",
        "https://example.invalid/2",
    }

    graph = mongo_backend.graph(
        GraphRequest(
            roots=("https://example.invalid/1",),
            max_nodes=5,
            max_edges=6,
        )
    )
    assert graph.metadata["backend"] == "mongodb"
    assert graph.payload["bounded"] is True
    assert len(graph.payload["nodes"]) <= 5
    assert all(ref.source_url for ref in graph.evidence)

    capability = mongo_backend.vector_capability()
    assert capability.available is True
    assert capability.index_name == "laclaugpt_vector"

    context = mongo_backend.context(ContextRequest("https://example.invalid/1", limit=5))
    assert context.metadata["available"] is True
    assert context.payload[0]["source_url"] == "https://example.invalid/2"
    assert context.evidence[0].source_url == "https://example.invalid/2"
    pipeline = mongo_backend.collection.last_pipeline
    assert "$vectorSearch" in pipeline[0]
    assert pipeline[0]["$vectorSearch"]["filter"] == {"project_id": "ai26"}


def test_missing_vector_index_only_disables_retrieval(tmp_path: Path) -> None:
    records = _frame().to_dict(orient="records")
    settings = _settings(
        tmp_path,
        storage_backend="mongodb",
        mongodb_uri="mongodb://synthetic.invalid:27017",
    )
    backend = MongoQueryBackend(
        settings=settings,
        client=FakeClient(FakeCollection(records, vector=False)),
    )
    assert backend.vector_capability().available is False
    assert not backend.context(ContextRequest("https://example.invalid/1")).payload
    assert not backend.graph(GraphRequest(max_nodes=5, max_edges=5)).payload.get("error")


def test_graph_lookup_is_depth_and_limit_bounded(
    mongo_backend: MongoQueryBackend,
) -> None:
    mongo_backend.graph_lookup(["Actor:alice"], depth=99, limit=999999)
    pipeline = mongo_backend.graph_collection.last_pipeline
    lookup = pipeline[2]["$graphLookup"]
    assert lookup["maxDepth"] == mongo_backend.settings.graph_max_depth - 1
    assert pipeline[1]["$limit"] == mongo_backend.settings.graph_max_edges
    assert lookup["restrictSearchWithMatch"] == {"project_id": "ai26"}


def test_storage_backend_never_exposes_uri_in_safe_summary(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        storage_backend="mongodb",
        mongodb_uri="mongodb://secret-host.invalid:27017/?tls=true",
    )
    summary = settings.safe_summary()
    assert summary["storage_backend"] == "mongodb"
    assert "secret-host" not in repr(summary)


def test_streamlit_pages_do_not_issue_mongodb_queries_directly() -> None:
    root = Path(__file__).parents[1] / "src" / "laclaugpt_visualization"
    ui_sources = [
        (root / "app.py").read_text(encoding="utf-8"),
        (root / "pages" / "Graph_Context_Explorer.py").read_text(encoding="utf-8"),
    ]
    for source in ui_sources:
        assert "MongoClient" not in source
        assert "$graphLookup" not in source
        assert "$vectorSearch" not in source
        assert "pymongo" not in source
