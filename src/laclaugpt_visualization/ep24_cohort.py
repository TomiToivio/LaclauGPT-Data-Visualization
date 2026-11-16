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
    """Is this row one of the approved identities for its country?

    Membership is decided by the roster, the ``monday500:<country>:<id>`` storage key and the row's
    own country — not by the ``dataset`` column. On the real checkpoint export that column carries
    the *pipeline* label (``ep2024_reprocess``); the cohort is named by the storage key and by the
    export manifest's ``producer_revision`` (``monday500_20261031``). Requiring the column to equal
    the cohort name rejected every row of the delivered 500-video export, which is how a guard
    becomes an outage.
    """
    value = str(row.get("_storage_id", "")).strip()
    return (
        value in approved
        and value.startswith(f"monday500:{country}:")
        and str(row.get("country", country)).casefold() == country
    )
