"""Minimal read-only MongoDB adapter for Phase 0 analysis outputs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from typing import Any, Iterable, Mapping

DEFAULT_LIMIT = 100
MAX_LIMIT = 500
STATUS_VALUES = {"analyzed", "awaiting-analysis", "error"}


class Phase0ConfigError(ValueError):
    """Raised when the shared Phase 0 MongoDB configuration is incomplete."""


@dataclass(frozen=True)
class Phase0MongoConfig:
    uri: str
    database: str
    project_id: str

    @property
    def collection_name(self) -> str:
        return f"laclaugpt2_{self.project_id}_scraper_collection"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Phase0MongoConfig":
        env = environ or os.environ
        values = {
            "uri": env.get("LACLAUGPT_MONGODB_URI", "").strip(),
            "database": env.get("LACLAUGPT_MONGODB_DATABASE", "").strip(),
            "project_id": env.get("LACLAUGPT_PROJECT_ID", "").strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            env_names = {
                "uri": "LACLAUGPT_MONGODB_URI",
                "database": "LACLAUGPT_MONGODB_DATABASE",
                "project_id": "LACLAUGPT_PROJECT_ID",
            }
            required = ", ".join(env_names[name] for name in missing)
            raise Phase0ConfigError(f"Missing required Phase 0 configuration: {required}")
        return cls(**values)


@dataclass(frozen=True)
class Phase0Filters:
    status: str | None = None
    start_date: datetime | str | None = None
    end_date: datetime | str | None = None
    actor: str | None = None
    arena: str | None = None
    ai_formation: str | None = None
    language: str | None = None

    def to_query(self) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if self.status:
            if self.status not in STATUS_VALUES:
                raise ValueError(
                    f"Unsupported analysis status {self.status!r}; "
                    f"expected one of {sorted(STATUS_VALUES)}"
                )
            if self.status == "analyzed":
                query["phase0.discourse.status"] = "ok"
            elif self.status == "error":
                query["phase0.discourse.status"] = "error"
            else:
                query["$or"] = [
                    {"phase0.discourse": {"$exists": False}},
                    {"phase0.discourse.status": {"$exists": False}},
                ]

        date_query: dict[str, Any] = {}
        if self.start_date is not None:
            date_query["$gte"] = _coerce_datetime(self.start_date)
        if self.end_date is not None:
            date_query["$lte"] = _coerce_datetime(self.end_date)
        if date_query:
            query["source_date"] = date_query

        for field, value in (
            ("actor_name", self.actor),
            ("arena", self.arena),
            ("ai_formation", self.ai_formation),
            ("language", self.language),
        ):
            if value:
                query[field] = value
        return query


def _coerce_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    text = value.strip()
    if not text:
        raise ValueError("date filter must not be empty")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid ISO date/datetime: {value!r}") from exc


def normalize_phase0_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable Phase 0 view model without exposing MongoDB _id."""
    source_url = record.get("source_url")
    phase0 = record.get("phase0") if isinstance(record.get("phase0"), Mapping) else {}
    discourse = phase0.get("discourse") if isinstance(phase0.get("discourse"), Mapping) else {}
    raw_status = discourse.get("status")

    if raw_status == "ok":
        analysis_status = "analyzed"
    elif raw_status == "error":
        analysis_status = "error"
    else:
        analysis_status = "awaiting-analysis"

    return {
        "source_url": source_url,
        "document_id": record.get("document_id"),
        "source_date": record.get("source_date"),
        "source_name": record.get("source_name"),
        "source_type": record.get("source_type"),
        "source_feed_url": record.get("source_feed_url"),
        "source_title": record.get("source_title"),
        "source_text": record.get("source_text"),
        "source_summary": record.get("source_summary"),
        "source_author": record.get("source_author"),
        "source_categories": record.get("source_categories"),
        "actor_name": record.get("actor_name"),
        "actor_type": record.get("actor_type"),
        "arena": record.get("arena"),
        "ai_formation": record.get("ai_formation"),
        "political_formation": record.get("political_formation"),
        "country": record.get("country"),
        "language": record.get("language"),
        "collected_at": record.get("collected_at"),
        "normalized_text": record.get("normalized_text"),
        "content_hash": record.get("content_hash"),
        "metadata": record.get("metadata"),
        "analysis_status": analysis_status,
        "phase0": dict(phase0),
        "phase0_summary_raw": record.get("phase0_summary_raw"),
        "phase0_summary": record.get("phase0_summary"),
        "phase0_summary_validated": record.get("phase0_summary_validated"),
        "phase0_discourse_raw": record.get("phase0_discourse_raw"),
        "phase0_discourse": record.get("phase0_discourse"),
        "phase0_ontology": record.get("phase0_ontology"),
    }


class Phase0MongoReader:
    """Small read-only adapter around the shared Phase 0 scraper collection."""

    def __init__(self, config: Phase0MongoConfig, *, client: Any | None = None) -> None:
        self.config = config
        self._client = client
        self._owns_client = client is None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from pymongo import MongoClient
            except ImportError as exc:
                raise RuntimeError(
                    "PyMongo is required for the Phase 0 MongoDB reader; "
                    "install laclaugpt-data-visualization[remote]"
                ) from exc
            self._client = MongoClient(
                self.config.uri,
                serverSelectionTimeoutMS=1500,
                connectTimeoutMS=1500,
                appname="laclaugpt-phase0-visualization",
            )
        return self._client

    def find(
        self,
        filters: Phase0Filters | None = None,
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
        query = (filters or Phase0Filters()).to_query()
        projection = {"_id": False}
        collection = self._get_client()[self.config.database][self.config.collection_name]
        cursor: Iterable[Mapping[str, Any]] = collection.find(query, projection).limit(limit)
        return [normalize_phase0_record(record) for record in cursor]

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "Phase0MongoReader":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
