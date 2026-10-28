"""Validate a private EP24 Mongo dashboard export before switching the live data root.

Source: LaclauGPT-Multimodal-Analysis/ep24_mongo_dashboard_export.py.
This module never opens a Mongo connection or publishes research data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

COUNTRIES = ("fi", "pl", "pt")


def validate(root: Path) -> dict:
    root = Path(root)
    manifest_path = root / "MANIFEST.json"
    if not manifest_path.is_file() or not (root / "combined.csv").is_file():
        raise ValueError("Expected MANIFEST.json and combined.csv in the same private export directory")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("generated_at") or not manifest.get("contract"):
        raise ValueError("Manifest missing producer contract or generation timestamp")
    if manifest.get("record_unit") != "video":
        raise ValueError("Expected one row per video")
    counts = manifest.get("record_counts") or {}
    sources = manifest.get("inputs") or {}
    coverage = manifest.get("stage_coverage") or {}
    if not all(c in counts and c in sources and c in coverage for c in COUNTRIES):
        raise ValueError("Missing FI/PL/PT coverage in manifest")
    frame = pd.read_csv(root / "combined.csv", dtype=str, keep_default_na=False)
    if not {"record_key", "country", "video_id"}.issubset(frame.columns):
        raise ValueError("Combined export lacks canonical record identity/country")
    if frame["record_key"].eq("").any() or frame["record_key"].duplicated().any():
        raise ValueError("Empty or duplicate record_key")
    if frame["video_id"].eq("").any():
        raise ValueError("Empty video_id")
    if not set(frame["country"]).issubset(set(COUNTRIES)):
        raise ValueError("Unexpected country in FI/PL/PT export")
    report = {"contract": manifest["contract"], "generated_at": manifest["generated_at"],
              "countries": {}, "total": len(frame)}
    for c in COUNTRIES:
        actual = int((frame["country"] == c).sum())
        expected = int(counts[c].get("exported", -1))
        if expected != actual:
            raise ValueError(f"{c}: manifest exported={expected}, combined.csv={actual}")
        if actual == 0:
            raise ValueError(f"{c}: no exported records; refusing incomplete dashboard refresh")
        subset = root / f"{c}.csv"
        if not subset.is_file():
            raise ValueError(f"{c}: missing country export")
        country_frame = pd.read_csv(subset, dtype=str, keep_default_na=False)
        if len(country_frame) != actual or not (country_frame["country"] == c).all():
            raise ValueError(f"{c}: country CSV differs from combined export")
        if set(country_frame["record_key"]) != set(frame.loc[frame["country"] == c, "record_key"]):
            raise ValueError(f"{c}: record identities disagree")
        report["countries"][c] = {
            "exported": actual, "invalid_ids": int(counts[c].get("invalid_ids", 0)),
            "duplicates": int(counts[c].get("duplicates", 0)),
            "stage_coverage": coverage[c],
            "unavailable_stages": sources[c].get("stage_unavailable", []),
        }
    if int(manifest.get("records", -1)) != len(frame):
        raise ValueError("Manifest total disagrees with combined export")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_dir", type=Path)
    args = parser.parse_args()
    try:
        report = validate(args.export_dir)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"EP24 refresh validation failed: {exc}\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
