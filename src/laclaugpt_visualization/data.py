"""Reusable data loading and normalization helpers.

This module is intentionally independent from the old monolithic LaclauGPT
package. It accepts flat researcher exports and canonical-ish JSON records and
normalizes common columns used by dashboards.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .config import Settings

_LIST_COLUMNS = (
    "entities",
    "topics",
    "signifiers",
    "nodal_points",
    "discourses",
    "imaginaries",
    "formations",
    "us",
    "frontier",
    "affects",
    "sentiment_labels",
    "uncertainties",
)


def _as_list(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple | set):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass
        return [part.strip() for part in text.split(";") if part.strip()]
    return [str(value)]


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize common LaclauGPT visualization columns without mutating input."""
    normalized = frame.copy()
    for column in _LIST_COLUMNS:
        if column not in normalized:
            normalized[column] = [[] for _ in range(len(normalized))]
        else:
            normalized[column] = normalized[column].map(_as_list)

    if "source_timestamp" in normalized:
        normalized["source_timestamp"] = pd.to_datetime(
            normalized["source_timestamp"], errors="coerce", utc=True
        )

    for column in ("document_id", "summary", "source_author", "source_platform"):
        if column not in normalized:
            normalized[column] = ""
        normalized[column] = normalized[column].fillna("").astype(str)

    if "searchable_text" not in normalized:
        normalized["searchable_text"] = normalized.apply(_searchable_text, axis=1)
    return normalized


def _searchable_text(row: pd.Series) -> str:
    fields: list[str] = []
    for key in (
        "document_id",
        "summary",
        "source_author",
        "source_platform",
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


def load_frame(source: str | Path, settings: Settings | None = None) -> pd.DataFrame:
    """Load CSV, JSON/JSONL, Parquet, or SQLite data and normalize it."""
    path = Path(source)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix in {".jsonl", ".ndjson"}:
        frame = pd.read_json(path, lines=True)
    elif suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else payload.get("records", [payload])
        frame = pd.DataFrame(records)
    elif suffix == ".parquet":
        frame = pd.read_parquet(path)
    elif suffix in {".sqlite", ".sqlite3", ".db"}:
        frame = load_sqlite(path)
    else:
        raise ValueError(f"unsupported visualization input: {path}")
    return normalize_frame(frame)


def load_sqlite(path: str | Path, table: str = "annotations") -> pd.DataFrame:
    """Load the default annotations table from SQLite."""
    with sqlite3.connect(Path(path)) as connection:
        frame = pd.read_sql_query(f'SELECT * FROM "{table}"', connection)
    return frame


def explode_labels(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Return label counts for a normalized list-valued column."""
    if column not in frame:
        return pd.DataFrame(columns=[column, "count"])
    exploded = frame[[column]].explode(column).dropna()
    exploded = exploded[exploded[column].astype(str).str.strip().ne("")]
    counts = exploded[column].value_counts().rename_axis(column).reset_index(name="count")
    return counts


def filter_frame(
    frame: pd.DataFrame,
    *,
    query: str = "",
    platforms: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Apply lightweight researcher-facing filters."""
    result = frame
    if query.strip():
        needle = query.casefold()
        result = result[result["searchable_text"].str.casefold().str.contains(needle, na=False)]
    if platforms:
        allowed = {str(value) for value in platforms}
        result = result[result["source_platform"].isin(allowed)]
    return result
