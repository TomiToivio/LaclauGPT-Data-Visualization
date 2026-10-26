#!/usr/bin/env python3
"""EP24 FI/PL/PT demo export — the documented entrypoint (issue #195, Part 1).

This is a **thin adapter**, not a second exporter. The implementation lives in
`scripts/ep24/export_visualization_data.py` (streaming, two-pass primary-row selection, coverage
manifest, child tables). This wrapper exists because the runbook and the deployment examples call
`export_demo.py --finland … --poland … --portugal … --output …`, and because real exports need two
things the earlier version got wrong:

* **country values in the producer's own casing** — a real Polish frame says `Poland`, not `poland`,
  and a real shared frame holds every country, so an exact lowercase match aborted the whole export;
* **a shared source file** — the Portuguese rows live inside the shared `:8501` export, so a country
  needs to be selected out of a file that also carries Finland, Poland, Sweden, …

Both are handled here without changing the documented CLI. Extra flags:
`--filter-country VALUE` (repeatable, `country=Value`) and `--profile` (`reprocessed`/`legacy`).

Usage:

    python scripts/ep24/export_demo.py \\
        --finland /private/input/finland.csv \\
        --poland  /private/input/poland.csv:legacy \\
        --portugal /private/input/shared_8501.csv:legacy \\
        --filter-country portugal=Portugal \\
        --output /private/LaclauGPT-Private/analysis/ep24/dashboard/export
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_streaming import COUNTRIES
from export_streaming import main as export_main


def _country_values(path: Path) -> list[str]:
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        reader.fieldnames = [name.lstrip("\ufeff") for name in (reader.fieldnames or ())]
        return [row.get("country", "") or "" for row in reader]


def _is_legacy(path: Path) -> bool:
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        names = {name.lstrip("\ufeff") for name in (csv.DictReader(handle).fieldnames or ())}
    # the legacy 75-column frame is identified by its whisper/OCR columns, not by the absence of a
    # reprocessed status column: a small synthetic frame may legitimately carry neither.
    return "whisper_transcript" in names and "preprocess_status" not in names


def export(inputs: dict[str, Path], output: Path) -> dict:
    """Programmatic entrypoint with the historical contract (`tests/test_ep24_export_demo.py`).

    The contract it keeps: a country mismatch is an error, a row without `video_id`/`_storage_id` is
    excluded and counted, and `records.jsonl` mirrors the index. Everything else is delegated to the
    streaming exporter, so there is still exactly one implementation.
    """
    output = Path(output)
    argv: list[str] = []
    for country in COUNTRIES:
        path = Path(inputs[country])
        values = {value.strip().casefold() for value in _country_values(path) if value.strip()}
        if values and values != {country}:
            raise ValueError(f"{path}: country mismatch in {len(_country_values(path))} rows")
        spec = f"{country}={path}:legacy" if _is_legacy(path) else f"{country}={path}"
        argv += ["--source", spec]
        if values:
            argv += ["--filter-country", f"{country}={values.pop().title() if False else next(iter(values))}"]
    # the historical contract is an allowlist projection: unknown/scratch columns are excluded
    # rather than failing the build, and they are listed in the manifest as excluded fields.
    argv += ["--output", str(output), "--require-video-id", "--allow-unaccounted"]
    code = export_main(argv)
    if code != 0:
        raise RuntimeError(f"export failed with status {code}")

    manifest = json.loads((output / "MANIFEST.json").read_text(encoding="utf-8"))
    counts = {c: manifest["record_counts"].get(c, {}) for c in COUNTRIES}
    children = manifest.get("children") or {}
    index_rows = list(csv.DictReader((output / "combined.csv").open(encoding="utf-8")))
    # The historical shape keeps every stage field inline in the row. The canonical export keeps long
    # stage output in the text bundle instead, so widen the compatibility frame from it.
    stage_fields = _stage_fields(output)
    for row in index_rows:
        row.update(stage_fields.get(row["record_key"], {}))
    _rewrite_frame(output / "combined.csv", index_rows)
    with (output / "records.jsonl").open("w", encoding="utf-8") as handle:
        for row in index_rows:
            handle.write(json.dumps({"record_id": row["record_key"], **row},
                                    ensure_ascii=False) + "\n")
    return {
        "records": sum(int(counts[c].get("exported", 0)) for c in COUNTRIES),
        "invalid_id_rows_excluded": sum(int(counts[c].get("invalid_ids", 0)) for c in COUNTRIES),
        "by_country": {c: int(counts[c].get("exported", 0)) for c in COUNTRIES},
        "child_rows": {table: sum(int((children.get(c) or {}).get(table, 0)) for c in COUNTRIES)
                       for table in ("entities", "discourse_claims", "dna_statements",
                                     "sna_nodes", "sna_edges")},
        "stage_status": manifest.get("stage_coverage"),
        "included_fields": sorted(index_rows[0].keys()) if index_rows else [],
        "excluded_fields": sorted({name for c in COUNTRIES
                                   for name in (manifest["inputs"].get(c, {})
                                                .get("dropped_reasons") or {})}),
        "manifest_path": str(output / "MANIFEST.json"),
    }


def _stage_fields(output: Path) -> dict[str, dict[str, str]]:
    """record_key -> {field: value} from the gzipped text bundle (used for the compat projection)."""
    import gzip
    fields: dict[str, dict[str, str]] = {}
    bundle = output / "text.jsonl.gz"
    if not bundle.is_file():
        return fields
    with gzip.open(bundle, "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            key = record.get("record_key")
            if not key:
                continue
            merged: dict[str, str] = {}
            for step, block in record.items():
                if step in {"record_key", "country", "profile"} or not isinstance(block, dict):
                    continue
                for name, value in block.items():
                    merged.setdefault(name, value)
            fields[key] = merged
    return fields


def _rewrite_frame(path: Path, rows: list[dict[str, str]]) -> None:
    header: list[str] = []
    for row in rows:
        for name in row:
            if name not in header:
                header.append(name)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, restval="")
        writer.writeheader()
        writer.writerows(rows)


def build_argv(args: argparse.Namespace) -> list[str]:
    argv: list[str] = []
    for country in COUNTRIES:
        spec = getattr(args, country, None)
        if spec:
            argv += ["--source", f"{country}={spec}"]
    for pair in args.filter_country:
        argv += ["--filter-country", pair]
    if args.profile:
        argv += ["--profile", args.profile]
    argv += ["--output", str(args.output)]
    return argv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    for country in COUNTRIES:
        parser.add_argument(f"--{country}", type=str, default=None, metavar="PATH[:PROFILE]",
                            help="Roihu cumulative CSV, or a legacy/shared frame with :legacy")
    parser.add_argument("--output", type=Path, required=True, help="private output directory")
    parser.add_argument("--filter-country", action="append", default=[], metavar="COUNTRY=VALUE",
                        help="keep only rows whose in-file country equals VALUE")
    parser.add_argument("--profile", choices=("reprocessed", "legacy"), default=None,
                        help="profile for sources without a :profile suffix")
    args = parser.parse_args(argv)
    if not any(getattr(args, country, None) for country in COUNTRIES):
        parser.error("at least one of --finland/--poland/--portugal is required")
    return export_main(build_argv(args))


if __name__ == "__main__":
    raise SystemExit(main())
