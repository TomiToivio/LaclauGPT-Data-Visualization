#!/usr/bin/env python3
"""EP24 FI/PL/PT visualization export (issue #195, Part 1).

Reads completed EP24 results **read-only** and writes the normalized dataset the existing
reprocessed dashboard already consumes (`src/laclaugpt_visualization/ep24_reprocessed.py`).
The dashboard is the customer here: this script produces `finland.csv`, `poland.csv`,
`portugal.csv`, `combined.csv`, `records.jsonl` plus child tables and a manifest, and nothing
else. It deliberately does **not** define a second data model.

Guarantees:

* **Read-only** on the source. No writes, no schema changes, no Mongo/Redis/GPU/Ollama need.
* **No fabricated IDs.** A row without any identity field is excluded and *counted*, never
  given a synthetic key.
* **Country namespaces never merge.** Identity is namespaced by dataset/country/source type,
  so the same numeric video id in FI and PL is two records.
* **An allowlist, not a dump.** Transient/backend fields are dropped, and the reason is written
  into the data dictionary. Provenance and status are kept.
* **Deterministic.** Same input, same bytes; rows sorted by stable identity.
* **No secrets, no real data.** Credentials are never read. Real exports belong in the private
  repository, not here.

Usage:
    python scripts/ep24/export_visualization_data.py \
        --countries finland poland portugal \
        --input /path/to/ep24/results \
        --output /path/to/ep24/export
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "ep24-visualization-export/1.0"

#: Identity candidates in priority order (mirrors the dashboard's `identity()`).
IDENTITY_FIELDS = ("allas_filename", "video_id", "_storage_id", "source_url")

#: Namespace components — a record may never join across these.
NAMESPACE_FIELDS = ("dataset", "country", "source_type")

#: Required stage fields per stage, as the dashboard detects coverage. Kept in sync by test.
STAGE_FIELDS: dict[int, tuple[str, ...]] = {
    0: ("_storage_id", "video_id", "allas_filename"),
    1: ("preprocess_status",),
    2: ("frame_analysis_status",),
    3: ("vllm_video_status",),
    4: ("summary_quality_status", "summary_analysis"),
    5: ("postprocess_entities", "postprocess_themes", "postprocess_summary_md"),
    6: ("laclau_status", "laclau_structured_json"),
    7: ("dna_status", "dna_statements_json"),
    8: ("sna_edges_json",),
    9: (),
}

#: Kept fields: identity, provenance, status, evidence, and the human-readable result columns.
ALLOWLIST: tuple[str, ...] = (
    *IDENTITY_FIELDS,
    *NAMESPACE_FIELDS,
    "title", "author_username", "account_type", "source_platform", "source_language",
    "published_at", "created_at", "duration_seconds", "video_duration", "language",
    "sequence_number", "source_recording", "political_preference",
    "entities", "themes", "researcher_note",
    "asr_transcript", "asr_translation", "asr_translated", "asr_language", "ocr_1",
    "frame_file", "frame_timestamp_seconds", "frame_analysis_1", "frame_quality_status",
    "vllm_video_analysis", "vllm_video_markdown_analysis", "vllm_video_structured_json",
    "summary_analysis", "summary_summary_md", "summary_quality_reason",
    "preprocess_status", "frame_analysis_status", "vllm_video_status",
    "summary_quality_status", "postprocess_entities", "postprocess_themes",
    "postprocess_summary_md", "positive", "neutral", "negative",
    "ep24_entity_resolution_json", "ep24_entity_ids", "ep24_entity_canonical_names",
    "ep24_entity_unresolved_json", "ep24_sentiment_targets_json",
    "processing_status", "processing_status_reason",
    "laclau_status", "laclau_structured_json", "laclau_summary_md",
    "laclau_abstention_reason", "laclau_formula_conditions_met",
    "formula_of_populism_analysis", "formula_of_populism_us", "formula_of_populism_frontier",
    "dna_status", "dna_statements_json", "dna_analysis_markdown", "dna_statement_count",
    "sna_nodes_json", "sna_edges_json", "sna_analysis_markdown",
    "rdf_ttl_path", "error_status", "error_message", "provenance", "schema_version",
)

#: Dropped by design, with the reason recorded in the data dictionary.
EXCLUDED: dict[str, str] = {
    "prompt": "transient model prompt, not a finding",
    "state_blob": "temporary pipeline state",
    "working_tensors": "backend-only working data, not meaningful to a researcher",
    "verbose_cache": "verbose cache of intermediate output",
    "embedding": "high-dimensional backend artifact; not a scalar finding",
}

#: One-to-many children: (json field, table name, stable child id prefix).
CHILDREN: tuple[tuple[str, str], ...] = (
    ("postprocess_entities", "entities_model"),
    ("postprocess_themes", "themes_model"),
    ("dna_statements_json", "dna_statements"),
    ("sna_nodes_json", "sna_nodes"),
    ("sna_edges_json", "sna_edges"),
)

COUNTRY_FILES = {"finland": "fi", "poland": "pl", "portugal": "pt"}


def clean(value: Any) -> str:
    """Scalar text, with the dashboard's missing-value vocabulary treated as absent."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    text = str(value).strip()
    return "" if text.lower() in {"", "none", "nan", "null", "<na>"} else text


def row_identity(row: Mapping[str, Any], record_unit: str = "video") -> str:
    """Namespaced record identity: stable media or individual ingest run."""
    if record_unit not in {"video", "ingest"}:
        raise ValueError("record_unit must be video or ingest")
    namespace = "|".join(clean(row.get(f)).casefold() for f in NAMESPACE_FIELDS)
    if record_unit == "ingest":
        native = clean(row.get("_storage_id"))
        if not native:
            return ""
        return f"{namespace}|ingest|{native}"
    media = clean(row.get("allas_filename"))
    video = clean(row.get("video_id"))
    if media:
        parts = (media, video)
    elif video:
        parts = (video, clean(row.get("source_type")),
                 clean(row.get("source_recording")), clean(row.get("sequence_number")))
    else:
        return ""
    digest = hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:20]
    return f"{namespace}|video|{digest}"


def completeness_score(row: Mapping[str, Any]) -> int:
    """Choose the most complete run without conflating output with quality."""
    return sum(bool(clean(row.get(field))) for field in ALLOWLIST
               if field not in IDENTITY_FIELDS and field not in NAMESPACE_FIELDS)


def distinct_media_count(rows: Iterable[Mapping[str, Any]]) -> int:
    return len({key for row in rows if (key := row_identity(row, "video"))})


def read_csv_source(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def read_sqlite_source(path: Path, table: str) -> Iterator[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        connection.row_factory = sqlite3.Row
        for record in connection.execute(f'SELECT * FROM "{table}"'):
            yield dict(record)
    finally:
        connection.close()


def load_country(input_dir: Path, country: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load one country's rows, read-only, from whichever adapter exists."""
    rows: list[dict[str, Any]] = []
    notes: dict[str, Any] = {"country": country, "source": None, "found": False}
    for candidate in (input_dir / f"{country}.csv", input_dir / COUNTRY_FILES[country] / f"{country}.csv"):
        if candidate.is_file():
            rows = list(read_csv_source(candidate))
            notes.update(source=str(candidate), found=True, adapter="csv")
            break
    if not notes["found"]:
        for candidate in (input_dir / f"{country}.sqlite3", input_dir / f"{country}.db"):
            if candidate.is_file():
                try:
                    rows = list(read_sqlite_source(candidate, "results"))
                    notes.update(source=str(candidate), found=True, adapter="sqlite")
                except sqlite3.Error as error:
                    notes.update(error=f"sqlite read failed: {error}")
                break
    for row in rows:
        # A blank country must inherit the file's country: otherwise the namespace is empty
        # and FI/PL rows with the same native id would collide across countries.
        if not clean(row.get("country")):
            row["country"] = country
    return rows, notes


def project(row: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the allowlist, then fill absent allowlisted fields with ''."""
    return {field: row.get(field, "") for field in ALLOWLIST if field not in EXCLUDED}


def normalise(rows: Iterable[Mapping[str, Any]], country: str,
              record_unit: str = "video") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Choose one most-complete run per media, or preserve each ingest."""
    by_identity: dict[str, dict[str, Any]] = {}
    scores: dict[str, int] = {}
    invalid = duplicates = 0
    media: set[str] = set()
    for original in rows:
        row = dict(original)
        row["country"] = clean(row.get("country")) or country
        identity = row_identity(row, record_unit)
        if not identity:
            invalid += 1
            continue
        media_key = row_identity(row, "video")
        if media_key:
            media.add(media_key)
        projected = project(row)
        projected["record_id"] = identity
        projected["country"] = row["country"]
        projected["schema_version"] = SCHEMA_VERSION
        score = completeness_score(row)
        if identity in by_identity:
            duplicates += 1
            if score <= scores[identity]:
                continue
        by_identity[identity] = projected
        scores[identity] = score
    ordered = [by_identity[key] for key in sorted(by_identity)]
    return ordered, {"invalid_identity": invalid, "duplicate_rows_collapsed": duplicates,
                     "kept": len(ordered), "records": len(ordered),
                     "distinct_media": len(media), "record_unit": record_unit}


#: A status field exists for these stages; a non-success status is *not* coverage.
STATUS_FIELD_BY_STAGE = {1: "preprocess_status", 2: "frame_analysis_status",
                         3: "vllm_video_status", 4: "summary_quality_status",
                         6: "laclau_status", 7: "dna_status"}
SUCCESS_STATUSES = {"done", "ok", "success", "complete", "completed", "available"}


def stage_coverage(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """How many rows can actually show each stage — completeness, not interpretation.

    A row whose stage status says ``failed`` has a status *field* but produced no result, so it
    must not be counted as coverage. Counting it would turn a failure into apparent completion,
    which is the one error the issue forbids most explicitly.
    """
    coverage: dict[str, Any] = {}
    for stage, fields in STAGE_FIELDS.items():
        if not fields:
            coverage[str(stage)] = {"present": None,
                                    "note": "file-based artifact; not inferred from rows"}
            continue
        status_field = STATUS_FIELD_BY_STAGE.get(stage)
        if status_field:
            succeeded = [row for row in rows
                         if clean(row.get(status_field)).casefold() in SUCCESS_STATUSES]
            failed = [row for row in rows
                      if clean(row.get(status_field))
                      and clean(row.get(status_field)).casefold() not in SUCCESS_STATUSES]
            coverage[str(stage)] = {"present": len(succeeded), "of": len(rows),
                                    "failed_or_other": len(failed),
                                    "status_field": status_field, "fields": list(fields)}
        else:
            present = sum(1 for row in rows if any(clean(row.get(f)) for f in fields))
            coverage[str(stage)] = {"present": present, "of": len(rows), "fields": list(fields)}
    return coverage


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = ["record_id", *ALLOWLIST]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: clean(row.get(field)) for field in fields})


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def parse_children(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return next((part for part in value.values() if isinstance(part, list)), [])
    text = clean(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return []
    if isinstance(parsed, dict):
        parsed = next((value for value in parsed.values() if isinstance(value, list)), [])
    return parsed if isinstance(parsed, list) else []


def write_children(output: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Normalized child tables with stable ids — never a concatenated cell dump."""
    counts: dict[str, int] = {}
    for field, table in CHILDREN:
        records: list[dict[str, Any]] = []
        for row in rows:
            for index, child in enumerate(parse_children(row.get(field))):
                if not isinstance(child, dict):
                    continue
                record = {"parent_record_id": row["record_id"],
                          "child_id": f"{row['record_id']}#{index}"}
                record.update({key: clean(val) for key, val in child.items()})
                records.append(record)
        records.sort(key=lambda item: item["child_id"])
        if records:
            fields = sorted({key for record in records for key in record})
            with (output / f"{table}.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(records)
        counts[table] = len(records)
    return counts


def write_data_dictionary(output: Path) -> None:
    lines = ["# EP24 visualization export — data dictionary", "",
             f"Schema: `{SCHEMA_VERSION}`", "",
             "## Kept fields", ""]
    lines += [f"- `{field}`" for field in ALLOWLIST]
    lines += ["", "## Dropped fields, and why", ""]
    lines += [f"- `{field}` — {reason}" for field, reason in EXCLUDED.items()]
    lines += ["", "## Identity", "",
              ("`record_id` = namespaced `dataset|country|source_type|native id`. A row with no "
               "native id is excluded and counted in `qa.json`; no id is ever fabricated."),
              "", "## Stages", "",
              ("Stage coverage counts rows whose stage status reports success, plus rows "
               "carrying the required fields where a stage has no status. It is a completeness "
               "measure, **not** a claim that a finding is valid.")]
    (output / "DATA_DICTIONARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def export(input_dir: Path, output: Path, countries: Sequence[str], record_unit: str = "video") -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    combined: list[dict[str, Any]] = []
    report: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "record_unit": record_unit, "countries": {}}

    for country in countries:
        rows, notes = load_country(input_dir, country)
        normalised, stats = normalise(rows, country, record_unit)
        notes.update(stats)
        if not notes.get("found"):
            notes["note"] = "no source file found; exported as an empty country, not as zero findings"
        report["countries"][country] = notes
        write_csv(output / f"{country}.csv", normalised)
        combined.extend(normalised)

    combined.sort(key=lambda row: row["record_id"])
    write_csv(output / "combined.csv", combined)
    write_jsonl(output / "records.jsonl", combined)
    report["records"] = len(combined)
    report["distinct_media"] = sum(report["countries"][c]["distinct_media"] for c in countries)
    report["children"] = write_children(output, combined)
    report["rows"] = {"combined": len(combined),
                      "by_country": {c: report["countries"][c].get("kept", 0) for c in countries}}
    report["stage_coverage"] = stage_coverage(combined)
    report["stage_coverage_by_country"] = {
        country: stage_coverage([row for row in combined if row["country"] == country])
        for country in countries
    }
    report["sources"] = {c: report["countries"][c].get("source") for c in countries}
    (output / "manifest.json").write_text(json.dumps({"record_unit": record_unit,
        "records": report["records"], "distinct_media": report["distinct_media"],
        "countries": {c: {"records": report["countries"][c]["records"],
                         "distinct_media": report["countries"][c]["distinct_media"]}
                      for c in countries}}, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    write_data_dictionary(output)
    (output / "qa.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                                    encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export EP24 FI/PL/PT visualization data (read-only).")
    parser.add_argument("--countries", nargs="+", default=list(COUNTRY_FILES), choices=list(COUNTRY_FILES))
    parser.add_argument("--input", required=True, type=Path, help="directory holding completed EP24 results")
    parser.add_argument("--output", required=True, type=Path, help="destination directory for the export")
    parser.add_argument("--record-unit", choices=("video", "ingest"), default="video",
                        help="video (research default) or ingest (pipeline observability)")
    args = parser.parse_args(argv)

    report = export(args.input, args.output, args.countries, args.record_unit)
    rows = report["rows"]
    print(f"exported {rows['combined']} rows from {args.input} -> {args.output}")
    for country, count in rows["by_country"].items():
        entry = report["countries"][country]
        state = "ok" if entry.get("found") else "NO SOURCE"
        print(f"  {country:9} {count:5} rows  [{state}]  invalid-id: {entry.get('invalid_identity', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
