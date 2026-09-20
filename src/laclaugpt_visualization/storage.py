"""Storage adapters for visualization inputs and cached artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .config import Settings
from .data import load_frame, normalize_frame
from .query_backends import BackendUnavailable, MongoQueryBackend


def load_local_frame(settings: Settings) -> pd.DataFrame:
    """Load the portable local visualization input without contacting remote services."""
    if settings.data_backend == "sqlite" and settings.sqlite_path.exists():
        return load_frame(settings.sqlite_path, settings)
    roots = [settings.analysis_data_dir, settings.data_dir]
    candidates: list[Path] = []
    for root in roots:
        if root and Path(root).exists():
            for suffix in ("*.jsonl", "*.ndjson", "*.csv", "*.json", "*.parquet"):
                candidates.extend(sorted(Path(root).glob(suffix)))
    return load_frame(candidates[0], settings) if candidates else normalize_frame(pd.DataFrame())



def load_canonical_mongodb(settings: Settings, *, limit: int | None = 100) -> pd.DataFrame:
    """Load only canonical Phase 1 records without compatibility-store fallback."""
    if not settings.mongodb_uri:
        raise BackendUnavailable("Canonical Phase 1 browser requires LACLAUGPT_VIS_MONGODB_URI.")
    backend = MongoQueryBackend.from_settings(settings)
    return backend.records(limit=limit).payload

def load_mongodb(settings: Settings, query: dict[str, Any] | None = None) -> pd.DataFrame:
    """Load project-scoped records, falling back only when ``storage_backend=auto``.

    Explicit MongoDB mode fails clearly. Auto mode treats MongoDB as the preferred shared
    backend but preserves local/CSV operation if the optional driver or remote service is
    unavailable.
    """
    settings.validate_remote_requirements()
    if query:
        # Backward-compatible ad hoc query path. It remains bounded to the current project.
        try:
            from pymongo import MongoClient
            from pymongo.errors import PyMongoError
        except ImportError as exc:
            if settings.storage_backend == "auto":
                return load_local_frame(settings)
            raise RuntimeError("Install laclaugpt-data-visualization[remote] for MongoDB") from exc
        client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=settings.mongodb_connect_timeout_ms,
            connectTimeoutMS=settings.mongodb_connect_timeout_ms,
            appname="laclaugpt-data-visualization",
        )
        try:
            collection = client[settings.mongodb_database][settings.resolved_mongodb_collection]
            project_query = dict(query)
            project_query["project_id"] = settings.project_id
            records = list(collection.find(project_query, {"_id": False}))
            return normalize_frame(pd.DataFrame(records))
        except (PyMongoError, ConnectionError, OSError, TimeoutError) as exc:
            if settings.storage_backend == "auto":
                return load_local_frame(settings)
            raise BackendUnavailable("Configured MongoDB is unavailable.") from exc
        finally:
            client.close()

    try:
        backend = MongoQueryBackend.from_settings(settings)
        product = backend.records()
        return product.payload
    except BackendUnavailable:
        if settings.storage_backend == "auto":
            return load_local_frame(settings)
        raise


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
