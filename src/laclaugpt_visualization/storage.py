"""Storage adapters for visualization inputs and cached artifacts."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

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


@dataclass(frozen=True)
class ArtifactReference:
    """Safe, read-only description of a canonical artifact reference."""

    reference: str
    display_reference: str
    key: str | None
    filename: str
    content_type: str | None = None
    downloadable: bool = false
    reason: str = ""


_ARTIFACT_REF_KEYS = ("object_ref", "media_ref", "file_ref", "ref", "key", "path", "url")


def _reference_value(value: Any) -> tuple[str, str | None]:
    if isinstance(value, str):
        return value.strip(), None
    if not isinstance(value, Mapping):
        return "", None
    reference = next(
        (str(value.get(key)).strip() for key in _ARTIFACT_REF_KEYS if value.get(key)),
        "",
    )
    content_type = value.get("content_type") or value.get("mime_type") or value.get("media_type")
    return reference, str(content_type).strip() if content_type else None


def safe_artifact_reference(reference: str) -> str:
    """Strip credentials/query fragments before a reference is shown in UI or logs."""
    reference = str(reference or "").strip()
    if not reference:
        return ""
    parsed = urlsplit(reference)
    if not parsed.scheme:
        return reference
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _project_s3_key(settings: Settings, reference: str) -> tuple[str | None, str]:
    """Resolve a reference into the current project's object prefix without escaping it."""
    parsed = urlsplit(reference)
    if parsed.scheme in {"s3", "allas"}:
        if parsed.netloc and settings.s3_bucket and parsed.netloc != settings.s3_bucket:
            return None, "reference points to a different bucket"
        raw_key = parsed.path.lstrip("/")
    elif parsed.scheme:
        return None, "reference is not an S3/Allas object"
    else:
        raw_key = reference.lstrip("/")

    parts = [part for part in raw_key.split("/") if part not in {"", "."}]
    if not parts or ".." in parts:
        return None, "reference is empty or escapes its project prefix"
    clean = "/".join(parts)
    prefix = f"{settings.s3_prefix_root.strip('/')}/{settings.project_id}/"
    root = f"{settings.s3_prefix_root.strip('/')}/"
    if clean.startswith(root) and not clean.startswith(prefix):
        return None, "reference belongs to a different project"
    key = clean if clean.startswith(prefix) else f"{prefix}{clean}"
    return key, ""


def resolve_artifact_reference(settings: Settings, value: Any) -> ArtifactReference:
    """Resolve one canonical media/file reference without contacting object storage."""
    reference, content_type = _reference_value(value)
    display = safe_artifact_reference(reference)
    filename = Path(urlsplit(reference).path or reference).name or "artifact"
    if not reference:
        return ArtifactReference("", "", None, filename, content_type, False, "empty reference")
    if settings.object_backend != "s3":
        return ArtifactReference(
            reference, display, None, filename, content_type, False, "object storage is not configured"
        )
    if not settings.s3_endpoint_url or not settings.s3_bucket:
        return ArtifactReference(
            reference, display, None, filename, content_type, False, "S3/Allas endpoint or bucket is unavailable"
        )
    key, reason = _project_s3_key(settings, reference)
    return ArtifactReference(reference, display, key, filename, content_type, key is not None, reason)


def artifact_references(row: Mapping[str, Any]) -> list[Any]:
    """Collect canonical artifact references without treating source_url as an object."""
    found: list[Any] = []
    seen: set[str] = set()
    for field in ("media_references", "file_references", "frames"):
        values = row.get(field) or []
        if not isinstance(values, list):
            values = [values]
        for value in values:
            reference, _ = _reference_value(value)
            if not reference or reference in seen:
                continue
            seen.add(reference)
            found.append(value)
    for field in ("video_file", "audio_file"):
        value = row.get(field)
        reference, _ = _reference_value(value)
        if reference and reference not in seen:
            seen.add(reference)
            found.append(value)
    return found


def download_s3_object(settings: Settings, key: str, destination: str | Path) -> Path:
    """Download one current-project S3/Allas object; never uploads or rewrites source identity."""
    settings.validate_remote_requirements()
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install laclaugpt-data-visualization[remote] for S3") from exc

    client_kwargs: dict[str, Any] = {"endpoint_url": settings.s3_endpoint_url}
    if settings.s3_region:
        client_kwargs["region_name"] = settings.s3_region
    if settings.s3_access_key_id:
        client_kwargs["aws_access_key_id"] = settings.s3_access_key_id
    if settings.s3_secret_access_key:
        client_kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
    client = boto3.client("s3", **client_kwargs)
    resolved_key, reason = _project_s3_key(settings, key)
    if resolved_key is None:
        raise ValueError(f"unsafe S3/Allas artifact reference: {reason}")
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(settings.s3_bucket, resolved_key, str(target))
    return target
