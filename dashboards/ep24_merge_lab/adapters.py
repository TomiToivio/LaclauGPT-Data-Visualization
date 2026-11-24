"""Read the legacy dashboards through an activated curated mapping (#300, deliverable 3).

This is the only place the curated labels meet the legacy data, and it is strictly read-only:

* the source CSV is opened for reading and never for writing, and :func:`write_canonicalised`
  refuses an output path that resolves to the source;
* canonicalisation happens on read, so the untouched file keeps serving the old dashboards;
* duplicate spellings *inside one record* collapse to one occurrence, which is what prevents an
  alias merge from inflating a count.

Writing a canonicalised copy is possible — a researcher may want one — but it always lands in a
new file with the mapping version in its name, and it never becomes an input to anything unless a
human points a dashboard at it.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from .export import MAPPING_SCHEMA
from .sources import split_labels

csv.field_size_limit(10**9)


def load_mapping(export_dir: Path) -> dict[str, dict[str, str]]:
    """Read ``alias_map.json`` into ``category -> {alias casefolded: canonical}``."""
    payload = json.loads((export_dir / "alias_map.json").read_text(encoding="utf-8"))
    if payload.get("schema") != MAPPING_SCHEMA:
        raise ValueError(f"unsupported mapping schema {payload.get('schema')!r}")
    mapping: dict[str, dict[str, str]] = {}
    for row in payload["mapping"]:
        mapping.setdefault(row["category"], {})[row["alias"].casefold()] = row["canonical"]
    return mapping


def canonicalise_labels(
    labels: Iterable[str],
    mapping: dict[str, str],
    *,
    dedupe: bool = True,
) -> list[str]:
    """Map labels to their canonical form, keeping order; optionally drop duplicates.

    Deduplication is per record: *Orpo* and *Petteri Orpo* in the same row are one person said
    twice, and counting both is exactly the double count that alias collapsing must avoid.
    """
    result: list[str] = []
    seen: set[str] = set()
    for label in labels:
        canonical = mapping.get(label.casefold(), label)
        if dedupe and canonical.casefold() in seen:
            continue
        seen.add(canonical.casefold())
        result.append(canonical)
    return result


def canonicalise_row(
    row: dict[str, str],
    *,
    columns: dict[str, str],
    mapping: dict[str, dict[str, str]],
    separator: str = ",",
) -> dict[str, str]:
    """One row of a legacy table with its label lists canonicalised."""
    result = dict(row)
    for category, column in columns.items():
        if column not in result:
            continue
        labels = split_labels(result.get(column), separator)
        if not labels:
            continue
        result[column] = separator.join(
            canonicalise_labels(labels, mapping.get(category, {}))
        )
    return result


def iter_canonicalised(
    source: Path,
    *,
    columns: dict[str, str],
    mapping: dict[str, dict[str, str]],
    separator: str = ",",
    encoding: str = "utf-8",
) -> Iterator[dict[str, str]]:
    """Stream a legacy table through the mapping. The source is opened read-only."""
    with source.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield canonicalise_row(row, columns=columns, mapping=mapping, separator=separator)


def write_canonicalised(
    source: Path,
    out_dir: Path,
    *,
    columns: dict[str, str],
    export_dir: Path,
    separator: str = ",",
    encoding: str = "utf-8",
) -> Path:
    """Write a canonicalised copy of ``source`` beside it — never over it.

    The output name carries the export id and the source digest, so two mappings never produce the
    same file and a reader can tell which mapping produced what.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{source.stem}.canonical-{export_dir.name}{source.suffix}"
    if target.resolve() == source.resolve():
        raise ValueError("refusing to overwrite the legacy source")
    mapping = load_mapping(export_dir)
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))

    rows = 0
    with source.open("r", encoding=encoding, newline="") as handle, target.open(
        "w", encoding="utf-8", newline=""
    ) as output:
        reader = csv.DictReader(handle)
        assert reader.fieldnames
        writer = csv.DictWriter(output, fieldnames=reader.fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in reader:
            writer.writerow(
                canonicalise_row(row, columns=columns, mapping=mapping, separator=separator)
            )
            rows += 1

    (target.with_suffix(target.suffix + ".provenance.json")).write_text(
        json.dumps(
            {
                "source": source.name,
                "source_sha256": source_digest,
                "export_id": export_dir.name,
                "mapping_version": manifest.get("mapping_version", ""),
                "rows": rows,
                "columns": columns,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def count_preview(
    source: Path,
    *,
    columns: dict[str, str],
    mapping: dict[str, dict[str, str]],
    separator: str = ",",
    encoding: str = "utf-8",
    sample_rows: int = 0,
) -> dict[str, Any]:
    """What activating this mapping would change: labels before and after, per category."""
    before: dict[str, int] = {category: 0 for category in columns}
    after: dict[str, int] = {category: 0 for category in columns}
    distinct_before: dict[str, set[str]] = {category: set() for category in columns}
    distinct_after: dict[str, set[str]] = {category: set() for category in columns}
    rows = 0
    # Read the raw rows: `before` must be the labels the legacy dashboard shows, not the mapped
    # ones, or the preview would compare the mapping with itself.
    with source.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows += 1
            for category, column in columns.items():
                raw = split_labels(row.get(column), separator)
                mapped = canonicalise_labels(raw, mapping.get(category, {}))
                before[category] += len(raw)
                after[category] += len(mapped)
                distinct_before[category].update(item.casefold() for item in raw)
                distinct_after[category].update(item.casefold() for item in mapped)
            if sample_rows and rows >= sample_rows:
                break
    return {
        "rows": rows,
        "categories": {
            category: {
                "labels_before": before[category],
                "labels_after": after[category],
                "distinct_before": len(distinct_before[category]),
                "distinct_after": len(distinct_after[category]),
                "collapsed": before[category] - after[category],
            }
            for category in columns
        },
    }
