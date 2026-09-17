"""Deterministic adapter for private legacy art-analysis CSV files."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from scripts.legacy.art.parse_analysis import parse_analysis
from scripts.legacy.common import CONTRACT_VERSION, provenance, stable_id, write_json


def preprocess(input_path: Path) -> dict:
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    records: list[dict] = []
    concepts: list[dict] = []
    for row_number, row in enumerate(rows, start=2):
        source_id = (row.get("source_id") or row.get("id") or row.get("url") or "").strip()
        source_id = source_id or stable_id(row_number, row.get("country", ""), row.get("summary_analysis", ""))
        country = (row.get("country") or "").strip()
        analysis = row.get("summary_analysis") or row.get("analysis") or ""
        records.append({
            "source_id": source_id,
            "country": country,
            "summary_analysis_raw": analysis,
            "provenance": provenance(source_field="legacy_row", status="source_observed"),
        })
        concepts.extend(parse_analysis(analysis, source_id=source_id))
    edges = Counter((record["country"], concept["canonical_term"], concept["concept_family"])
                    for record in records for concept in concepts if concept["source_id"] == record["source_id"])
    concept_edges = [
        {"country": country, "canonical_term": term, "concept_family": family, "weight": weight}
        for (country, term, family), weight in sorted(edges.items())
    ]
    return {
        "contract_version": CONTRACT_VERSION,
        "dataset": "art",
        "geometry": {"orbital": "decorative", "semantic_points": "analytical_when_present"},
        "records": records,
        "concepts": concepts,
        "concept_edges": concept_edges,
        "quality": {"rows": len(records), "parsed_concepts": len(concepts)},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    payload = preprocess(args.input)
    write_json(args.output / "view_model.json", payload, overwrite=args.overwrite)
    write_json(args.output / "provenance.json", {
        "contract_version": CONTRACT_VERSION,
        "dataset": "art",
        "source": str(args.input),
        "parser": "markdown_sections_v1",
        "raw_preserved": True,
    }, overwrite=args.overwrite)
    print(json.dumps(payload["quality"], sort_keys=True))


if __name__ == "__main__":
    main()
