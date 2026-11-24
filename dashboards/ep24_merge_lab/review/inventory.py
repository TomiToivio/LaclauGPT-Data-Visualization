"""Freeze the review inventory, and turn a run into decision units (#311).

A "decision unit" is what a reviewer is asked about: one cluster (a merged set of labels, which
may be wrong and may be split), or one unresolved label with the alternatives the matcher already
found. Reviewing units rather than raw strings is what keeps the work tractable — 8 035 units
instead of ~30 000 labels — while every label still appears in exactly one unit, so coverage is
countable per category, country and reviewer.

Freezing matters more than it looks: the issue requires that every reviewer of a batch sees the
same snapshot, and that the release can be reproduced from the same frozen decisions. So the
inventory is written once, hashed, and every later stage refers to it by digest.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

INVENTORY_SCHEMA = "ep24.merge_lab.review_inventory/1"

csv.field_size_limit(10**9)


@dataclass
class DecisionUnit:
    """One thing a reviewer judges."""

    unit_id: str
    category: str
    kind: str  # "cluster" | "candidate"
    labels: list[str]
    canonical: str
    occurrences: int
    confidence: float
    method: str
    countries: list[str] = field(default_factory=list)
    #: For a candidate: the alternatives the string matcher suggested.
    alternatives: list[str] = field(default_factory=list)
    reason: str = ""

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _unit_id(category: str, kind: str, labels: list[str]) -> str:
    body = json.dumps([category, kind, sorted(labels)], ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def units_from_run(run_dir: Path) -> list[DecisionUnit]:
    """Every cluster and every unresolved label of a run, as decision units."""
    units: list[DecisionUnit] = []
    for category in ("entity", "person", "theme", "topic", "sentiment"):
        for row in _rows(run_dir / f"canonical_{category}.csv"):
            members = [item for item in row["members"].split(" | ") if item]
            units.append(
                DecisionUnit(
                    unit_id=_unit_id(category, "cluster", members),
                    category=category,
                    kind="cluster",
                    labels=members,
                    canonical=row["canonical"],
                    occurrences=int(row["occurrences"] or 0),
                    confidence=float(row["confidence"] or 0),
                    method=row["method"],
                )
            )
        for row in _rows(run_dir / f"review_{category}.csv"):
            alternatives = [
                part.strip().rsplit(" (", 1)[0]
                for part in row.get("alternatives", "").split("|")
                if part.strip()
            ]
            units.append(
                DecisionUnit(
                    unit_id=_unit_id(category, "candidate", [row["label"], *alternatives]),
                    category=category,
                    kind="candidate",
                    labels=[row["label"]],
                    canonical=row["label"],
                    occurrences=int(row.get("occurrences") or 0),
                    confidence=float(row.get("occurrences") or 0) and 0.0,
                    method="candidate",
                    alternatives=alternatives,
                    reason=row.get("reason", ""),
                )
            )
    return units


def freeze(run_dir: Path, out_path: Path, units: list[DecisionUnit]) -> dict[str, Any]:
    """Write the inventory once and return its digest-bearing header."""
    payload = {
        "schema": INVENTORY_SCHEMA,
        "frozen_at": datetime.now(UTC).isoformat(),
        "base_run": run_dir.name,
        "units": [unit.as_json() for unit in units],
    }
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    header = {
        "schema": INVENTORY_SCHEMA,
        "frozen_at": payload["frozen_at"],
        "base_run": run_dir.name,
        "digest": digest,
        "counts": {
            category: sum(1 for unit in units if unit.category == category)
            for category in ("entity", "person", "theme", "topic", "sentiment")
        },
        "kinds": {
            kind: sum(1 for unit in units if unit.kind == kind) for kind in ("cluster", "candidate")
        },
        "total": len(units),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({**header, "units": payload["units"]}, indent=1, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return header


def load_inventory(path: Path) -> tuple[dict[str, Any], list[DecisionUnit]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    units = [DecisionUnit(**item) for item in payload["units"]]
    header = {key: value for key, value in payload.items() if key != "units"}
    return header, units


def attach_countries(units: list[DecisionUnit], pooled: dict[str, list[Any]]) -> None:
    """Attach the countries each unit's labels were seen in, from a fresh extraction.

    A reviewer needs this: *Christian Democrats* is the German CDU only if the mention is German,
    and a Dutch one is a different party entirely. The run tables do not carry countries, so the
    harness extracts them once and stamps them onto the frozen inventory.
    """
    by_label: dict[str, set[str]] = {}
    for stats in pooled.values():
        for stat in stats:
            if stat.countries:
                by_label.setdefault(stat.label.casefold(), set()).update(stat.countries)
    for unit in units:
        countries: set[str] = set()
        for label in unit.labels:
            countries.update(by_label.get(label.casefold(), set()))
        unit.countries = sorted(countries)
