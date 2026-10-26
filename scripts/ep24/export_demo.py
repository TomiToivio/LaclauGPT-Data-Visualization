"""Produce privacy-local, normalized EP24 demo datasets from cumulative Roihu CSVs.

This never writes research data to GitHub. All paths are supplied by the operator.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
from laclaugpt_visualization.ep24_reprocessed import STAGES, identity, status, unpack, text

COUNTRIES = ("finland", "poland", "portugal")
ALIASES = {"fi": "finland", "pl": "poland", "pt": "portugal"}
BASE = ("dataset", "country", "source_type", "source_language", "video_id",
        "_storage_id", "allas_filename", "source_url", "created_at")
# Explicit allowlist: only final or inspection-critical results, never scratch/prompt blobs.
EXTRA = (
    "asr_translation", "asr_transcript", "ocr_1", "frame_file",
    "frame_analysis_1", "vllm_video_analysis", "summary_analysis",
    "postprocess_entities", "postprocess_themes", "postprocess_summary_md",
    "laclau_structured_json", "laclau_summary_md", "dna_statements_json",
    "sna_nodes_json", "sna_edges_json", "sna_analysis_markdown",
    "ep24_entity_ids", "ep24_entity_canonical_names",
)
CHILDREN = {
    "dna_statements_json": "dna_statements",
    "sna_nodes_json": "sna_nodes",
    "sna_edges_json": "sna_edges",
    "postprocess_entities": "entities",
    "postprocess_themes": "themes",
}


def _country(value):
    raw = text(value).casefold()
    return ALIASES.get(raw, raw)


def _read(path):
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        return pd.read_json(path, lines=True, dtype=False)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
    raise ValueError(f"Unsupported input: {path}")


def export(inputs, output):
    """Return manifest; fail fast for unrecognized files and absent input data."""
    output = Path(output)
    if not inputs:
        raise ValueError("Pass one or more source CSV/JSONL files")
    frames = []
    for name, path in inputs.items():
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        frame = _read(path)
        country = _country(name)
        if country not in COUNTRIES:
            raise ValueError(f"Unsupported country {name}")
        if "country" in frame:
            observed = frame["country"].map(_country)
            mismatched = observed[(observed != "") & (observed != country)]
            if not mismatched.empty:
                raise ValueError(f"{path}: country mismatch in {len(mismatched)} rows")
        frame["country"] = country
        frames.append(frame)
    source = pd.concat(frames, ignore_index=True)
    allowed = list(dict.fromkeys((*BASE, *EXTRA, *(k for _, keys in STAGES.values() for k in keys),
                                 "preprocess_status", "frame_analysis_status", "vllm_video_status",
                                 "summary_quality_status", "laclau_status", "dna_status")))
    present = [k for k in allowed if k in source]
    work = source[present].copy().fillna("")
    work["record_id"] = [identity(r) for r in work.to_dict("records")]
    invalid = work["record_id"].eq("") | work.get("video_id", pd.Series("", index=work.index)).astype(str).str.strip().eq("")
    invalid_count = int(invalid.sum())
    work = work.loc[~invalid].copy()
    duplicates = int(work.duplicated("record_id").sum())
    if duplicates:
        # Fail rather than silently discarding different versions/runs.
        raise ValueError(f"{duplicates} duplicate source identities; select one checkpoint/run per country")
    for step in STAGES:
        work[f"step_{step}_status"] = [
            status(row, step) if step != 9 else "unavailable (RDF files not in row export)"
            for row in work.to_dict("records")
        ]
    if work.empty:
        raise ValueError("No source records with valid video IDs")

    output.mkdir(parents=True, exist_ok=True)
    records = work.to_dict("records")
    with (output / "records.jsonl").open("w", encoding="utf-8") as f:
        for record in records:
            normalized = {key: unpack(value) if key.endswith("_json") else text(value)
                          for key, value in record.items()}
            f.write(json.dumps(normalized, ensure_ascii=False, default=str) + "\n")
    work.to_csv(output / "combined.csv", index=False)
    for country in COUNTRIES:
        work.loc[work["country"] == country].to_csv(output / f"{country}.csv", index=False)
    child_counts = {}
    for field, name in CHILDREN.items():
        rows = []
        for record in records:
            val = unpack(record.get(field))
            if isinstance(val, dict):
                val = next((v for v in val.values() if isinstance(v, list)), [])
            if not isinstance(val, list):
                continue
            for i, item in enumerate(val):
                rows.append({"record_id": record["record_id"], "country": record["country"],
                             "item_index": i, "item_json": json.dumps(item, ensure_ascii=False, default=str)})
        pd.DataFrame(rows, columns=["record_id", "country", "item_index", "item_json"]).to_csv(
            output / f"{name}.csv", index=False)
        child_counts[name] = len(rows)
    manifest = {
        "schema": "ep24-reprocessed-demo/1", "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_files": [str(path) for path in inputs.values()],
        "records": len(work), "invalid_id_rows_excluded": invalid_count,
        "by_country": {c: int((work["country"] == c).sum()) for c in COUNTRIES},
        "stage_status": {str(step): work[f"step_{step}_status"].value_counts().to_dict()
                         for step in STAGES},
        "child_rows": child_counts, "included_fields": present,
        "excluded_fields": sorted(set(source.columns) - set(present) - {"record_id"}),
        "notes": ["Stage 9 must be verified against actual RDF artifacts.",
                  "Availability does not imply researcher validation.",
                  "Treat exported records as restricted research data; do not commit."]
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in COUNTRIES:
        parser.add_argument(f"--{name}", type=Path, required=True, help="Roihu cumulative CSV or JSONL")
    parser.add_argument("--output", type=Path, required=True, help="Private output directory")
    args = parser.parse_args()
    print(json.dumps(export({c: getattr(args, c) for c in COUNTRIES}, args.output), indent=2))


if __name__ == "__main__":
    main()
