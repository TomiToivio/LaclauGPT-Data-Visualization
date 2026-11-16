"""Explicit Monday500 membership; never select a cohort by row position."""

from __future__ import annotations

import hashlib
from pathlib import Path

COUNTRIES = ("finland", "poland", "portugal")


def read_roster(path: Path) -> tuple[set[str], dict]:
    payload = path.read_bytes()
    ids = [line.strip() for line in payload.decode("utf-8-sig").splitlines() if line.strip()]
    if len(ids) != len(set(ids)):
        raise ValueError("Approved roster contains duplicate IDs")
    counts = dict.fromkeys(COUNTRIES, 0)
    for value in ids:
        parts = value.split(":")
        if len(parts) != 3 or parts[0] != "monday500" or parts[1] not in counts or not parts[2]:
            raise ValueError("Approved roster must contain monday500:<country>:<id> values")
        counts[parts[1]] += 1
    if any(count != 500 for count in counts.values()):
        raise ValueError("Approved roster must contain exactly 500 identities per FI/PL/PT country")
    return set(ids), {
        "schema": "ep24-approved-cohort/1",
        "dataset": "ep24_monday500_20261031",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "approved_counts": counts,
    }


def is_member(row, country: str, approved: set[str]) -> bool:
    value = str(row.get("_storage_id", "")).strip()
    return (
        value in approved
        and value.startswith(f"monday500:{country}:")
        and str(row.get("country", country)).casefold() == country
        and str(row.get("dataset") or "ep24_monday500_20261031") == "ep24_monday500_20261031"
    )
