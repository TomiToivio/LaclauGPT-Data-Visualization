"""Storage adapters for visualization inputs and cached artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .config import Settings
from .data import normalize_frame


def load_mongodb(settings: Settings, query: dict[str, Any] | None = None) -> pd.DataFrame:
    """Load records from MongoDB. Requires the ``remote`` extra."""
    settings.validate_remote_requirements()
    try:
        from pymongo import MongoClient
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install laclaugpt-data-visualization[remote] for MongoDB") from exc

    client = MongoClient(settings.mongodb_uri)
    try:
        collection = client[settings.mongodb_database][settings.mongodb_collection]
        records = list(collection.find(query or {}, {"_id": False}))
    finally:
        client.close()
    return normalize_frame(pd.DataFrame(records))


def redis_client(settings: Settings):
    """Return a Redis client when remote caching is enabled."""
    settings.validate_remote_requirements()
    try:
        import redis
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install laclaugpt-data-visualization[remote] for Redis") from exc
    return redis.from_url(settings.redis_url, decode_responses=True)


def download_s3_object(settings: Settings, key: str, destination: str | Path) -> Path:
    """Download an object from S3-compatible storage such as CSC Allas."""
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
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(settings.s3_bucket, key, str(target))
    return target
