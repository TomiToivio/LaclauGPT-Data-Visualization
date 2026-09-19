"""Data loading, canonical reconstruction, normalization and filtering."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from .canonical import flatten_canonical, reconstruct_canonical
from .config import Settings
from .legacy_ep24 import adapt as adapt_ep24
from .legacy_ep24 import looks_like_ep24

_LIST_COLUMNS = (
    "entities",
    "entity_mentions",
    "topics",
    "classifications",
    "signifiers",
    "nodal_points",
    "discourses",
    "imaginaries",
    "formations",
    "us",
    "them",
    "frontier",
    "affects",
    "sentiment_labels",
    "uncertainties",
    "abstentions",
    "relations",
    "ocr",
    "frames",
    "media_references",
    "file_references",
    "model_runs",
)


def _as_list(value: Any) -> list[Any]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text[:1] in {"[", "{"}:
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                pass
        return [part.strip() for part in text.split(";") if part.strip()]
    return [value]


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    candidate = reconstruct_canonical(record)
    if candidate.get("source_url") and (
        candidate.get("schema_version")
        or candidate.get("source")
        or candidate.get("content")
        or candidate.get("analysis")
    ):
        return flatten_canonical(candidate)
    if looks_like_ep24(record):
        return adapt_ep24(record)
    return record


def frame_from_records(records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Create the common view from canonical Mongo-like/Python documents.

    This is also the no-live-Mongo contract boundary: callers may pass documents
    returned by any storage adapter without exposing backend IDs as record identity.
    """
    clean: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        item.pop("_id", None)
        clean.append(item)
    return normalize_frame(pd.DataFrame(clean))


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize visualization columns without mutating the input frame.

    DataFrames are view-layer objects. Canonical rows are reconstructed first,
    including JSON-encoded nested sections from CSV/SQLite adapters.
    """
    if frame.empty:
        normalized = frame.copy()
    else:
        normalized = pd.DataFrame(
            [_normalize_record(dict(row)) for row in frame.to_dict(orient="records")]
        )

    for column in _LIST_COLUMNS:
        if column not in normalized:
            normalized[column] = [[] for _ in range(len(normalized))]
        else:
            normalized[column] = normalized[column].map(_as_list)

    for column in ("source_timestamp", "collection_timestamp", "analysis_timestamp"):
        if column in normalized:
            normalized[column] = pd.to_datetime(normalized[column], errors="coerce", utc=True)
        else:
            normalized[column] = pd.NaT

    defaults = {
        "document_id": "",
        "source_url": "",
        "schema_version": "",
        "summary": "",
        "source_text": "",
        "transcript": "",
        "translated_text": "",
        "source_author": "",
        "source_author_fullname": "",
        "source_platform": "",
        "source_type": "",
        "source_country": "",
        "source_language": "",
        "collector": "",
        "collection_method": "",
        "analysis_status": "collection-only",
        "review_status": "PROVISIONAL",
    }
    for column, default in defaults.items():
        if column not in normalized:
            normalized[column] = default
        normalized[column] = normalized[column].fillna(default).astype(str)

    # source_url is always the selection/review/export identity. document_id remains
    # only a compatibility alias for old view code.
    has_source = normalized["source_url"].ne("")
    normalized.loc[has_source, "document_id"] = normalized.loc[has_source, "source_url"]

    if "searchable_text" not in normalized:
        normalized["searchable_text"] = normalized.apply(_searchable_text, axis=1)
    return normalized


def _searchable_text(row: pd.Series) -> str:
    fields: list[str] = []
    for key in (
        "source_url",
        "summary",
        "source_text",
        "transcript",
        "source_author",
        "source_author_fullname",
        "source_platform",
        "source_type",
        "source_country",
        "entities",
        "topics",
        "signifiers",
        "discourses",
        "formations",
    ):
        value = row.get(key, "")
        if isinstance(value, list):
            fields.extend(str(item) for item in value)
        elif value:
            fields.append(str(value))
    return "\n".join(fields)


def _records_from_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        records = payload.get("records")
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]
        return [payload]
    raise ValueError("JSON visualization input must contain an object or list of objects")


def load_frame(source: str | Path, settings: Settings | None = None) -> pd.DataFrame:
    """Load canonical or bounded-legacy data into the common view model."""
    del settings
    path = Path(source)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix in {".jsonl", ".ndjson"}:
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return frame_from_records(records)
    elif suffix == ".json":
        return frame_from_records(_records_from_json(path))
    elif suffix == ".parquet":
        frame = pd.read_parquet(path)
    elif suffix in {".sqlite", ".sqlite3", ".db"}:
        frame = load_sqlite(path)
    else:
        raise ValueError(f"unsupported visualization input: {path}")
    return normalize_frame(frame)


def load_sqlite(path: str | Path, table: str = "annotations") -> pd.DataFrame:
    """Load a configured SQLite table without opening a connection at import time."""
    if not table.replace("_", "").isalnum():
        raise ValueError("SQLite table name must contain only letters, numbers or underscores")
    with sqlite3.connect(Path(path)) as connection:
        frame = pd.read_sql_query(f'SELECT * FROM "{table}"', connection)
    return frame


def explode_labels(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if column not in frame:
        return pd.DataFrame(columns=[column, "count"])
    exploded = frame[[column]].explode(column).dropna()
    exploded = exploded[exploded[column].astype(str).str.strip().ne("")]
    return exploded[column].value_counts().rename_axis(column).reset_index(name="count")


def filter_frame(
    frame: pd.DataFrame,
    *,
    query: str = "",
    platforms: Iterable[str] | None = None,
    countries: Iterable[str] | None = None,
    languages: Iterable[str] | None = None,
    authors: Iterable[str] | None = None,
    formations: Iterable[str] | None = None,
    entities: Iterable[str] | None = None,
    topics: Iterable[str] | None = None,
    signifiers: Iterable[str] | None = None,
    frontiers: Iterable[str] | None = None,
    start: Any | None = None,
    end: Any | None = None,
) -> pd.DataFrame:
    """Apply composable researcher-facing filters."""
    result = frame
    if query.strip():
        needle = query.casefold()
        result = result[result["searchable_text"].str.casefold().str.contains(needle, na=False)]
    scalar_filters = {
        "source_platform": platforms,
        "source_country": countries,
        "source_language": languages,
        "source_author": authors,
    }
    for column, selected in scalar_filters.items():
        if selected:
            allowed = {str(value) for value in selected}
            result = result[result[column].isin(allowed)]
    list_filters = {
        "formations": formations,
        "entities": entities,
        "topics": topics,
        "signifiers": signifiers,
        "frontier": frontiers,
    }
    for column, selected in list_filters.items():
        if selected:
            allowed = {str(value) for value in selected}
            result = result[
                result[column].map(
                    lambda values, allowed=allowed: bool(allowed.intersection(map(str, values)))
                )
            ]
    if start is not None:
        result = result[result["source_timestamp"] >= pd.Timestamp(start, tz="UTC")]
    if end is not None:
        result = result[result["source_timestamp"] <= pd.Timestamp(end, tz="UTC")]
    return result
