#!/usr/bin/env python3
"""Fail closed before launching a private EP24 Streamlit service."""
import csv
import json
import os
import sys
from pathlib import Path

COUNTRIES = {"finland", "poland", "portugal", "fi", "pl", "pt"}

def main() -> int:
    value = os.environ.get("LACLAUGPT_VIS_ANALYSIS_DATA_DIR", "")
    if not value:
        print("EP24 preflight: LACLAUGPT_VIS_ANALYSIS_DATA_DIR unset", file=sys.stderr)
        return 2
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        print("EP24 preflight: private data root missing", file=sys.stderr)
        return 2
    folders = (root, root / "data")
    combined = next((p / "combined.csv" for p in folders if (p / "combined.csv").is_file()), None)
    manifest = next((p / "MANIFEST.json" for p in folders if (p / "MANIFEST.json").is_file()), None)
    if combined is None or manifest is None:
        print("EP24 preflight: require combined.csv AND MANIFEST.json; refusing stale/unverified fallback", file=sys.stderr)
        return 2
    try:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(meta, dict) or not meta:
            raise ValueError("invalid manifest")
        with combined.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or "country" not in reader.fieldnames:
                raise ValueError("combined.csv lacks country column")
            counts = {}
            for row in reader:
                country = (row.get("country") or "").strip().casefold()
                if not country:
                    raise ValueError("record without country")
                counts[country] = counts.get(country, 0) + 1
        if not counts:
            raise ValueError("no rows in combined.csv")
        if not set(counts).issubset(COUNTRIES):
            raise ValueError("unexpected country in FI/PL/PT export")
        print("EP24 preflight OK: export present; countries=" + ",".join(sorted(counts))
              + "; records=" + str(sum(counts.values())))
        print("NOTE: production stage coverage and manifest counts require operator verification")
        return 0
    except (OSError, ValueError, csv.Error, json.JSONDecodeError) as exc:
        print("EP24 preflight rejected export: " + str(exc), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
