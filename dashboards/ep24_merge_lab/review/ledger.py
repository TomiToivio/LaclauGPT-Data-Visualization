"""The shared review ledger: who reviewed what, when, and what they said (#311).

The ledger is the collaboration surface the issue asks for: append-only JSONL, one line per
review or adjudication, attributable to a model and a run, resumable, and safe to read while
another agent writes. Three properties matter:

* **idempotent** — a (unit, reviewer) pair is reviewed once; re-running a batch skips what is
  already there instead of paying for it twice or, worse, double-counting an opinion;
* **honest** — a failed or rejected call appends an ``attempt`` record, never a review;
* **inspectable** — coverage is a query, not a promise: how many units have three reviews, per
  category, per reviewer, is computed from the file itself.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def append(path: Path, record: dict[str, Any]) -> None:
    """Append one record durably (a partial line would poison every later read)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": SCHEMA_VERSION,
        "at": datetime.now(UTC).isoformat(),
        **record,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_all(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            # A torn final line from a killed writer must not cost us the whole ledger.
            continue
        _ = number
    return records


def reviews_by_unit(path: Path) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in read_all(path):
        if record.get("type") != "review":
            continue
        index[record["unit_id"]].append(record)
    return index


def reviewed_pairs(path: Path) -> set[tuple[str, str]]:
    return {
        (record["unit_id"], record["reviewer"])
        for record in read_all(path)
        if record.get("type") == "review"
    }


def coverage(path: Path, units: Iterable[dict[str, Any]], required: int) -> dict[str, Any]:
    """How far the panel has got, counted from the ledger rather than from a plan."""
    by_unit = reviews_by_unit(path)
    per_category: dict[str, Counter[str]] = defaultdict(Counter)
    per_reviewer: Counter[str] = Counter()
    complete = 0
    partial = 0
    untouched = 0
    for unit in units:
        have = by_unit.get(unit["unit_id"], [])
        names = {item["reviewer"] for item in have}
        per_category[unit["category"]]["units"] += 1
        per_category[unit["category"]]["with_reviews"] += 1 if have else 0
        per_category[unit["category"]]["complete"] += 1 if len(names) >= required else 0
        for name in names:
            per_reviewer[name] += 1
        if len(names) >= required:
            complete += 1
        elif have:
            partial += 1
        else:
            untouched += 1
    attempts = [r for r in read_all(path) if r.get("type") == "attempt"]
    return {
        "units": complete + partial + untouched,
        "complete": complete,
        "partial": partial,
        "untouched": untouched,
        "required_reviews": required,
        "per_category": {key: dict(value) for key, value in sorted(per_category.items())},
        "per_reviewer": dict(per_reviewer),
        "failed_attempts": len(attempts),
    }


def disagreements(by_unit: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Units where the reviewers do not all reach the same decision or canonical name."""
    result: dict[str, list[dict[str, Any]]] = {}
    for unit_id, reviews in by_unit.items():
        decisions = {review["decision"] for review in reviews}
        canons = {review["canonical"].casefold() for review in reviews}
        if len(decisions) > 1 or len(canons) > 1:
            result[unit_id] = reviews
    return result
