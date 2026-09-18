"""Read-only MongoDB access for the Phase 0 visualization baseline."""

from __future__ import annotations

import os
from typing import Any


def settings() -> tuple[str, str, str]:
    uri = os.getenv("LACLAUGPT_MONGODB_URI") or os.getenv("MONGO_URI")
    database = os.getenv("LACLAUGPT_MONGODB_DATABASE") or os.getenv("MONGO_DB_NAME")
    project = os.getenv("LACLAUGPT_PROJECT_ID", "ai26")
    if not uri:
        raise RuntimeError("LACLAUGPT_MONGODB_URI is required")
    if not database:
        raise RuntimeError("LACLAUGPT_MONGODB_DATABASE is required")
    return uri, database, project


def collection_name(project: str) -> str:
    return f"laclaugpt2_{project}_scraper_collection"


def collection():
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError("PyMongo is required for Phase 0 visualization") from exc
    uri, database, project = settings()
    return MongoClient(uri)[database][collection_name(project)]


def analysis_status(document: dict[str, Any]) -> str:
    discourse = document.get("phase0", {}).get("discourse", {})
    status = discourse.get("status")
    if status == "ok":
        return "analyzed"
    if status == "error":
        return "error"
    return "awaiting"


def build_query(
    *, status: str | None = None, since: str | None = None, until: str | None = None,
    actor: str | None = None, arena: str | None = None, formation: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if status == "analyzed":
        query["phase0.discourse.status"] = "ok"
    elif status == "error":
        query["phase0.discourse.status"] = "error"
    elif status == "awaiting":
        query["phase0.discourse.status"] = {"$nin": ["ok", "error"]}
    if since or until:
        date_filter: dict[str, str] = {}
        if since:
            date_filter["$gte"] = since
        if until:
            date_filter["$lte"] = until
        query["source_date"] = date_filter
    for key, value in (
        ("actor_name", actor), ("arena", arena), ("ai_formation", formation),
        ("language", language),
    ):
        if value:
            query[key] = value
    return query


def list_documents(*, limit: int = 50, **filters: Any) -> list[dict[str, Any]]:
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    cursor = collection().find(build_query(**filters)).sort("source_date", -1).limit(limit)
    return list(cursor)


def find_document(identity: str) -> dict[str, Any] | None:
    return collection().find_one({"$or": [{"source_url": identity}, {"document_id": identity}]})
