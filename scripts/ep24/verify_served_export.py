#!/usr/bin/env python3
"""Does the directory a dashboard serves hold the export its manifest describes? (#263 §3)

The dashboard reads whatever export directory the unit points at, and nothing checked that directory against
the artifact in the private repository. Twice that gap mattered:

* the manifest declared a flat layout while the committed tree was per-country, so 26 of 28 declared files
  were missing and the manifest answered "yes, this is the export" to a question nobody could check;
* the host served a `combined.csv` build whose bytes matched no committed file, so "the data on :8502" was an
  artefact of the host rather than a release.

This tool answers the question without trusting either side: read the manifest, hash what is actually served,
and report every disagreement — missing file, wrong size, wrong hash, wrong row count — with a non-zero exit.

Read-only. Run it on the serving host before a deploy and after a data refresh.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def row_count(path: Path) -> int | None:
    """Data rows of a CSV, counted the way pandas reads them (one record per logical row)."""
    if path.suffix != ".csv":
        return None
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        return max(sum(1 for _ in csv.reader(handle)) - 1, 0)


def check(served: Path, manifest: Path) -> list[dict[str, str]]:
    """Every disagreement between the manifest and the served directory, as rows a report can print.

    A file the manifest does not mention is reported too: an extra file is how a stale `combined.csv` survives
    a layout change and keeps a dashboard serving a build nobody reviewed.
    """
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    declared: dict[str, dict] = payload.get("files") or payload
    problems: list[dict[str, str]] = []

    if not served.is_dir():
        return [{"file": str(served), "problem": "served directory does not exist"}]

    for name, expected in declared.items():
        path = served / name
        if not path.is_file():
            problems.append({"file": name, "problem": "declared by the manifest, missing from the served directory"})
            continue
        actual_bytes = path.stat().st_size
        if "bytes" in expected and actual_bytes != expected["bytes"]:
            problems.append({"file": name, "problem": f"size {actual_bytes} != {expected['bytes']}"})
            continue
        actual_hash = sha256_of(path)
        if expected.get("sha256") and actual_hash != expected["sha256"]:
            problems.append({"file": name, "problem": f"sha256 {actual_hash[:16]} != {expected['sha256'][:16]}"})
            continue
        if "rows" in expected:
            actual_rows = row_count(path)
            if actual_rows is not None and actual_rows != expected["rows"]:
                problems.append({"file": name, "problem": f"rows {actual_rows} != {expected['rows']}"})

    for path in sorted(served.rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(served).as_posix()
        if name == manifest.name or name in declared:
            continue
        problems.append({"file": name, "problem": "served but not declared by the manifest"})

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--served", required=True, type=Path, help="export directory the dashboard reads")
    parser.add_argument("--manifest", required=True, type=Path, help="manifest.json of the released export")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    declared = payload.get("files") or payload
    problems = check(args.served, args.manifest)

    if args.json:
        print(json.dumps({"served": str(args.served), "manifest": str(args.manifest),
                          "declared_files": len(declared), "problems": problems}, indent=2))
    else:
        if not problems:
            print(f"OK: {args.served} matches {args.manifest} ({len(declared)} files)")
        else:
            print(f"FAIL: {len(problems)} disagreement(s) between {args.served} and {args.manifest}")
            for problem in problems[:40]:
                print(f"  {problem['file']}: {problem['problem']}")
            if len(problems) > 40:
                print(f"  ... and {len(problems) - 40} more")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
