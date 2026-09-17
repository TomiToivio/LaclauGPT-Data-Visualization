"""Deterministic adapter for private legacy pledge CSVs.

Real inputs/outputs belong under ignored runtime paths. This module never infers
political alignment; it only preserves observed values and explicitly marks a
provided legacy-derived value when one exists.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from scripts.legacy.common import CONTRACT_VERSION, provenance, split_tokens, stable_id, write_json

ALIGNMENT_STATUS = {"observed", "legacy_derived", "missing"}
TOKEN_FIELDS = ("topics", "entities", "positive", "neutral", "negative")


def _first(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = (row.get(name) or "").strip()
        if value:
            return value
    return ""


def transform_row(row: dict[str, str], row_number: int) -> tuple[dict, list[dict]]:
    raw_alignment = _first(row, "political_alignment", "alignment")
    legacy_alignment = _first(row, "legacy_derived_alignment", "derived_alignment")
    if raw_alignment:
        alignment, status = raw_alignment, "observed"
    elif legacy_alignment:
        alignment, status = legacy_alignment, "legacy_derived"
    else:
        alignment, status = None, "missing"

    source_id = _first(row, "source_id", "id", "url") or stable_id(row_number, row.get("grievance", ""))
    record = {
        "source_id": source_id,
        "date": _first(row, "date", "created_at"),
        "country": _first(row, "country"),
        "platform": _first(row, "platform"),
        "grievance": _first(row, "grievance", "text"),
        "political_alignment_raw": raw_alignment or None,
        "political_alignment": alignment,
        "alignment_observation_status": status,
        "provenance": {
            "political_alignment": provenance(source_field="political_alignment", status=status),
            "record": provenance(source_field="legacy_row", status="source_observed"),
        },
    }
    tokens: list[dict] = []
    for field in TOKEN_FIELDS:
        for raw_token in split_tokens(row.get(field)):
            canonical = " ".join(raw_token.casefold().split())
            tokens.append(
                {
                    "source_id": source_id,
                    "field": field,
                    "raw_term": raw_token,
                    "canonical_term": canonical,
                    "provenance": provenance(source_field=field, status="normalized", rule="casefold_whitespace_v1"),
                }
            )
    return record, tokens


def preprocess(input_path: Path) -> dict:
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    records, tokens = [], []
    for index, row in enumerate(rows, start=2):
        record, row_tokens = transform_row(row, index)
        records.append(record)
        tokens.extend(row_tokens)
    statuses = Counter(record["alignment_observation_status"] for record in records)
    return {
        "contract_version": CONTRACT_VERSION,
        "dataset": "pledge",
        "records": records,
        "tokens": tokens,
        "quality": {"rows": len(records), "alignment_status": dict(sorted(statuses.items()))},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    payload = preprocess(args.input)
    write_json(args.output / "view_model.json", payload, overwrite=args.overwrite)
    write_json(
        args.output / "provenance.json",
        {"contract_version": CONTRACT_VERSION, "dataset": "pledge", "source": str(args.input), "derived_fields": ["political_alignment", "canonical_term"]},
        overwrite=args.overwrite,
    )
    print(json.dumps(payload["quality"], sort_keys=True))


if __name__ == "__main__":
    main()
