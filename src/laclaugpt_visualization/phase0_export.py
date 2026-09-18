"""Lightweight deterministic exports for Phase 0 visualization records."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

DEFAULT_EXPORT_DIR = Path("data/exports")
CSV_FIELDS = (
    "source_url",
    "source_date",
    "source_name",
    "source_title",
    "source_author",
    "actor_name",
    "arena",
    "ai_formation",
    "language",
    "analysis_status",
    "phase0",
    "phase0_summary",
    "phase0_discourse",
    "phase0_ontology",
)


def _json_default(value: Any) -> str:
    return str(value)


def _dumps(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def export_jsonl(records: Iterable[Mapping[str, Any]], path: str | Path | None = None) -> Path:
    output = Path(path) if path is not None else DEFAULT_EXPORT_DIR / "phase0.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(_dumps(dict(record)) + "\n")
    return output


def export_csv(records: Iterable[Mapping[str, Any]], path: str | Path | None = None) -> Path:
    output = Path(path) if path is not None else DEFAULT_EXPORT_DIR / "phase0.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            row = {field: record.get(field) for field in CSV_FIELDS}
            for field in ("phase0", "phase0_summary", "phase0_discourse", "phase0_ontology"):
                row[field] = _dumps(record.get(field))
            writer.writerow(row)
    return output


def export_phase0(
    records: Iterable[Mapping[str, Any]],
    *,
    fmt: str = "jsonl",
    path: str | Path | None = None,
) -> Path:
    if fmt == "jsonl":
        return export_jsonl(records, path)
    if fmt == "csv":
        return export_csv(records, path)
    raise ValueError("format must be 'jsonl' or 'csv'")
