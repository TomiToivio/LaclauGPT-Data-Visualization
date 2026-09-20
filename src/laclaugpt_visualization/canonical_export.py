"""Explicit, lossless interoperability exports for canonical Phase 1 records."""
from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping
from typing import Any

_CANONICAL_OBJECT_FIELDS = (
    "source_native_ids",
    "raw_capture",
    "source",
    "content",
    "intermediate",
    "analysis",
    "human_readable",
    "review",
    "legacy",
)
_CANONICAL_LIST_FIELDS = ("source_units", "alignments", "evidence", "provenance")
_CANONICAL_EXPORT_FIELDS = (
    "schema_version",
    "source_url",
    *_CANONICAL_OBJECT_FIELDS,
    *_CANONICAL_LIST_FIELDS,
)


class CanonicalExportError(ValueError):
    """Raised when a record cannot be exported without semantic coercion."""


def canonical_interop_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached canonical record suitable for interoperability export.

    This path is intentionally strict. It does not flatten records, synthesize missing
    sections, migrate Phase 0 compatibility documents, or promote backend identifiers.
    """
    source_url = record.get("source_url")
    if not isinstance(source_url, str) or not source_url.strip():
        raise CanonicalExportError("canonical export requires a non-empty source_url")

    if not record.get("schema_version"):
        raise CanonicalExportError("canonical export requires schema_version")

    for field in _CANONICAL_OBJECT_FIELDS:
        value = record.get(field, {})
        if value is not None and not isinstance(value, Mapping):
            raise CanonicalExportError(
                f"canonical export requires object field {field!r}; "
                f"got {type(value).__name__}"
            )

    for field in _CANONICAL_LIST_FIELDS:
        value = record.get(field, [])
        if value is not None and not isinstance(value, list):
            raise CanonicalExportError(
                f"canonical export requires list field {field!r}; "
                f"got {type(value).__name__}"
            )

    exported: dict[str, Any] = {}
    for field in _CANONICAL_EXPORT_FIELDS:
        if field in record:
            exported[field] = copy.deepcopy(record[field])

    # Interoperability exports never expose backend/runtime-only fields such as Mongo _id,
    # dataframe helper columns, search caches, or compatibility raw_record aliases.
    exported["source_url"] = source_url
    return exported


def canonical_jsonl(records: Iterable[Mapping[str, Any]]) -> str:
    """Serialize canonical records as deterministic UTF-8 JSON Lines."""
    lines = [
        json.dumps(
            canonical_interop_record(record),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for record in records
    ]
    return "".join(f"{line}\n" for line in lines)
