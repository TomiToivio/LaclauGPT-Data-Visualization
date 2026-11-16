"""Baseline audit of a private EP24 export (issue #405, workstream A/B).

The audit has to answer, per country and per stage: how many records are there, are the identities
unique, does every row parse to the header width, which stage columns are populated, and what the
status values actually say. It runs against the private files and prints **aggregates only** — counts,
distributions, column names — so the output can be published without carrying a single transcript,
username or researcher note.

    python scripts/ep24/audit_export_baseline.py --root <private export> --json out.json

Row counting uses :mod:`csv` parsing, not line counting: transcripts contain newlines inside quoted
fields, so ``wc -l`` reports 127 608 lines for Finland's 500-row export.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

COUNTRIES = ("finland", "poland", "portugal")

#: Stage name → the columns whose presence means that stage produced something.
STAGE_COLUMNS = {
    "0_ingest": ("allas_filename", "asr_transcript", "asr_language"),
    "1_preprocess": ("asr_transcript", "asr_model"),
    "2_frame": ("ocr_1", "frame_analysis_1"),
    "3_video": ("vllm_video_analysis", "vllm_video_status"),
    "4_summary": ("summary_analysis", "summary_quality_status"),
    "5_postprocess": ("postprocess_entities", "postprocess_themes", "summary_summary_md"),
    "6_laclau": ("laclau_summary_md", "laclau_status", "laclau_structured_json"),
    "7_dna": ("dna_statements_json", "dna_statement_count", "dna_status"),
    "8_sna": ("sna_edges_json", "sna_analysis_markdown", "sna_status"),
    "9_rdf": ("rdf_document_uri", "rdf_status", "rdf_schema_version"),
}

STATUS_COLUMNS = ("processing_status", "preprocess_status", "frame_analysis_status",
                  "vllm_video_status", "summary_quality_status", "laclau_status", "dna_status",
                  "sna_status", "video_status", "video_quality_status")


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def country_file(root: Path, country: str) -> Path | None:
    """The country's CSV in either layout, or ``None`` when neither exists."""
    for candidate in (root / country / f"{country}.csv", root / f"{country}.csv"):
        if candidate.is_file():
            return candidate
    return None


def audit_country(root: Path, country: str, *, hashes: bool = False) -> dict[str, Any]:
    """Aggregate facts about one country's CSV. No cell contents are returned."""
    path = country_file(root, country)
    if path is None:
        return {"country": country, "present": False}

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        rows = [row for row in reader if any(row)]

    widths = Counter(len(row) for row in rows)
    index = {name: position for position, name in enumerate(header)}

    def column(row: Sequence[str], name: str) -> str:
        position = index.get(name)
        if position is None or position >= len(row):
            return ""
        return (row[position] or "").strip()

    identities = Counter(column(row, "_storage_id") for row in rows)
    countries = Counter(column(row, "country").lower() for row in rows)
    datasets = Counter(column(row, "dataset") for row in rows)

    stages: dict[str, Any] = {}
    for stage, columns in STAGE_COLUMNS.items():
        present_columns = [name for name in columns if name in index]
        populated = sum(1 for row in rows if any(column(row, name) for name in present_columns))
        stages[stage] = {
            "columns": present_columns,
            "populated": populated,
            "pct": round(100 * populated / len(rows), 1) if rows else None,
        }

    statuses: dict[str, dict[str, int]] = {}
    for name in STATUS_COLUMNS:
        if name in index:
            statuses[name] = dict(Counter(column(row, name) or "(empty)" for row in rows))

    result: dict[str, Any] = {
        "country": country,
        "present": True,
        "file": str(path.name),
        "bytes": path.stat().st_size,
        "columns": len(header),
        "rows": len(rows),
        "row_widths": {str(width): count for width, count in sorted(widths.items())},
        "rows_matching_header_width": widths.get(len(header), 0),
        "unique_identities": len({value for value in identities if value}),
        "empty_identities": identities.get("", 0),
        "duplicate_identities": sum(count - 1 for value, count in identities.items() if value and count > 1),
        "countries": dict(countries),
        "datasets": dict(datasets),
        "stages": stages,
        "statuses": statuses,
    }
    if hashes:
        result["sha256"] = sha256(path)
    return result


def audit_children(root: Path) -> dict[str, Any]:
    """Row and identity coverage of each child table, without reading payload cells."""
    directories = (root / "children", root)
    tables: dict[str, Any] = {}
    for name in ("entities", "themes", "discourse_items", "dna_statements", "sna_nodes",
                 "sna_edges", "sentiment_targets"):
        path = next((directory / f"{name}.csv" for directory in directories
                     if (directory / f"{name}.csv").is_file()), None)
        if path is None:
            tables[name] = {"present": False}
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [row for row in reader if any(value for value in row.values() if value)]
        sources = {str(row.get("source_key") or "") for row in rows if row.get("source_key")}
        tables[name] = {"present": True, "rows": len(rows), "distinct_source_keys": len(sources)}
    return tables


def audit_manifest(root: Path) -> dict[str, Any]:
    """The export's own claims, so the audit can compare them with the files."""
    for name in ("manifest.json", "MANIFEST.json"):
        path = root / name
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                return {"present": True, "readable": False}
            return {"present": True, "readable": True,
                    "keys": sorted(payload.keys()),
                    "producer_revision": payload.get("producer_revision"),
                    "exported_at": payload.get("exported_at") or payload.get("generated_at"),
                    "countries": sorted((payload.get("countries") or {}).keys())}
    return {"present": False}


def run(root: Path, *, hashes: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = {
        "contract": "ep24-export-audit/1",
        "root_name": root.name,
        "manifest": audit_manifest(root),
        "countries": [audit_country(root, country, hashes=hashes) for country in COUNTRIES],
        "children": audit_children(root),
    }
    present = [row for row in report["countries"] if row.get("present")]
    report["totals"] = {
        "countries_present": len(present),
        "rows": sum(row["rows"] for row in present),
        "unique_identities": sum(row["unique_identities"] for row in present),
        "rows_matching_header_width": sum(row["rows_matching_header_width"] for row in present),
        "countries_claiming_wrong_country": {
            row["country"]: {k: v for k, v in row["countries"].items() if k != row["country"]}
            for row in present
            if any(key != row["country"] for key in row["countries"])
        },
    }
    return report


def markdown(report: dict[str, Any]) -> str:
    """A publishable summary: counts and column names only, no source content."""
    lines = [f"# EP24 export audit — `{report['root_name']}`", ""]
    manifest = report["manifest"]
    if manifest.get("present"):
        lines.append(f"Manifest: producer revision `{manifest.get('producer_revision')}`, "
                     f"exported `{manifest.get('exported_at')}`, "
                     f"countries {', '.join(manifest.get('countries') or []) or 'not listed'}.")
    else:
        lines.append("Manifest: **absent** — the audit rests on the files alone.")
    lines += ["", "| country | rows | unique ids | empty ids | duplicates | columns | width ok |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in report["countries"]:
        if not row.get("present"):
            lines.append(f"| {row['country']} | — | — | — | — | — | missing |")
            continue
        lines.append(
            f"| {row['country']} | {row['rows']:,} | {row['unique_identities']:,} | "
            f"{row['empty_identities']} | {row['duplicate_identities']} | {row['columns']} | "
            f"{row['rows_matching_header_width']:,}/{row['rows']:,} |")
    lines += ["", "## Stage population (rows with any output column filled)", "",
              "| stage | " + " | ".join(row["country"] for row in report["countries"]) + " |",
              "| --- |" + " ---: |" * len(report["countries"])]
    for stage in STAGE_COLUMNS:
        cells = []
        for row in report["countries"]:
            if not row.get("present"):
                cells.append("—")
                continue
            entry = row["stages"][stage]
            cells.append(f"{entry['populated']:,} ({entry['pct']}%)")
        lines.append(f"| {stage} | " + " | ".join(cells) + " |")
    lines += ["", "## Child tables", "", "| table | rows | distinct source keys |", "| --- | ---: | ---: |"]
    for name, entry in report["children"].items():
        if entry.get("present"):
            lines.append(f"| {name} | {entry['rows']:,} | {entry['distinct_source_keys']:,} |")
        else:
            lines.append(f"| {name} | — | missing |")
    lines += ["", "Totals: " + json.dumps(report["totals"], sort_keys=True)]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True, type=Path, help="private export directory")
    parser.add_argument("--json", type=Path, default=None, help="write the full report here")
    parser.add_argument("--markdown", type=Path, default=None, help="write the summary here")
    parser.add_argument("--hashes", action="store_true", help="also hash each country CSV")
    parser.add_argument("--expect", action="append", default=[], metavar="COUNTRY=SHA256,SIZE",
                        help="assert a country's file digest and size (repeatable)")
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        print(f"not a directory: {args.root}", file=sys.stderr)
        return 2
    report = run(args.root, hashes=args.hashes or bool(args.expect))

    failures = []
    for expectation in args.expect:
        country, _, rest = expectation.partition("=")
        digest, _, size = rest.partition(",")
        entry = next((row for row in report["countries"] if row["country"] == country), None)
        if not entry or not entry.get("present"):
            failures.append(f"{country}: file missing")
            continue
        if entry.get("sha256") != digest:
            failures.append(f"{country}: sha256 {entry.get('sha256')} != {digest}")
        if size and str(entry.get("bytes")) != size.strip():
            failures.append(f"{country}: size {entry.get('bytes')} != {size.strip()}")

    summary = markdown(report)
    print(summary)
    if failures:
        print("EXPECTATION FAILURES:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(summary, encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
