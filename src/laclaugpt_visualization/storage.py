"""Storage adapters for visualization inputs and cached artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .config import Settings
from .data import normalize_frame


def load_mongodb(settings: Settings, query: dict[str, Any] | None = None) -> pd.DataFrame:
    """Load project-scoped records from MongoDB. Requires the ``remote`` extra."""
    settings.validate_remote_requirements()
    try:
        from pymongo import MongoClient
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install laclaugpt-data-visualization[remote] for MongoDB") from exc

    client = MongoClient(settings.mongodb_uri)
    try:
        collection = client[settings.mongodb_database][settings.resolved_mongodb_collection]
        project_query = dict(query or {})
        project_query["project_id"] = settings.project_id
        records = list(collection.find(project_query, {"_id": False}))
    finally:
        client.close()
    return normalize_frame(pd.DataFrame(records))


def redis_client(settings: Settings):
    """Return a Redis client when remote caching/control-plane access is enabled."""
    settings.validate_remote_requirements()
    try:
        import redis
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install laclaugpt-data-visualization[remote] for Redis") from exc
    return redis.from_url(settings.redis_url, decode_responses=True)


def redis_cache_key(settings: Settings, name: str) -> str:
    """Return a cache key isolated to the configured project."""
    return settings.distributed_namespace.redis_key("cache", name)


def redis_control_key(
    settings: Settings,
    document_type: str,
    name: str = "current",
) -> str:
    """Resolve common control-plane keys without duplicating naming rules."""
    namespace = settings.distributed_namespace
    if document_type == "manifest":
        return namespace.manifest_key(name)
    if document_type in {"collection", "analysis", "visualization"}:
        return namespace.settings_key(document_type, name)
    raise ValueError(f"unsupported control document type: {document_type}")


def download_s3_object(settings: Settings, key: str, destination: str | Path) -> Path:
    """Download an object from the configured project's S3/Allas prefix."""
    settings.validate_remote_requirements()
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install laclaugpt-data-visualization[remote] for S3") from exc

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    clean = key.lstrip("/")
    project_prefix = f"{settings.s3_prefix_root}/{settings.project_id}/"
    resolved_key = clean if clean.startswith(project_prefix) else f"{project_prefix}{clean}"
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(settings.s3_bucket, resolved_key, str(target))
    return target
