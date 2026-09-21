"""Canonical evidence/provenance status vocabulary.

All visualization modules must normalize validation, review, extraction, and inference
signals through this module.  The literals below are intentionally semantic: a record
being human-reviewed does not imply that every extracted edge/location was validated.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

HUMAN_VALIDATED = "human-validated"
HUMAN_REVIEWED = "human-reviewed"
INFERRED = "inferred"
EXTRACTED = "extracted"
SOURCE_PROVIDED = "source-provided"
GEOCODED = "geocoded"
UNRECORDED = "unrecorded"

CANONICAL_STATUSES = frozenset(
    {
        HUMAN_VALIDATED,
        HUMAN_REVIEWED,
        INFERRED,
        EXTRACTED,
        SOURCE_PROVIDED,
        GEOCODED,
        UNRECORDED,
    }
)

_VALIDATED_ALIASES = frozenset(
    {"validated", HUMAN_VALIDATED, "verified", "accepted", "canonical"}
)
_REVIEWED_ALIASES = frozenset({"human", HUMAN_REVIEWED, "reviewed"})
_INFERRED_ALIASES = frozenset({"inferred", "generated", "llm", "model"})
_EXTRACTED_ALIASES = frozenset({"observed", "extracted", "source"})
_REVIEWED_RECORD_STATUSES = frozenset({"ACCEPTED", "CANONICAL", "REVISED"})


def canonical_evidence_status(explicit: Any = "", review_status: Any = "") -> str:
    """Normalize one explicit provenance signal plus an optional record review fallback."""
    value = str(explicit or "").strip().casefold()
    if value in _VALIDATED_ALIASES:
        return HUMAN_VALIDATED
    if value in _REVIEWED_ALIASES:
        return HUMAN_REVIEWED
    if value in _INFERRED_ALIASES:
        return INFERRED
    if value in _EXTRACTED_ALIASES:
        return EXTRACTED
    if str(review_status or "").strip().upper() in _REVIEWED_RECORD_STATUSES:
        return HUMAN_REVIEWED
    return UNRECORDED


def canonical_edge_status(relation: Mapping[str, Any], review_status: Any = "") -> str:
    """Classify a relation without promoting record review to edge validation."""
    explicit = (
        relation.get("validation_status")
        or relation.get("status")
        or relation.get("provenance_type")
        or relation.get("origin")
        or ""
    )
    return canonical_evidence_status(explicit, review_status)


def canonical_coordinate_status(
    item: Mapping[str, Any],
    review_status: Any = "",
) -> str:
    """Classify coordinate provenance using the same evidence vocabulary."""
    if bool(item.get("human_validated")):
        return HUMAN_VALIDATED

    explicit = (
        item.get("coordinate_status")
        or item.get("validation_status")
        or item.get("status")
        or ""
    )
    normalized = canonical_evidence_status(explicit)
    if normalized != UNRECORDED:
        return normalized

    method = str(
        item.get("coordinate_method") or item.get("method") or item.get("origin") or ""
    ).strip().casefold()
    if method in {"source", SOURCE_PROVIDED, "native", "metadata"}:
        return SOURCE_PROVIDED
    if "geocod" in method:
        return GEOCODED
    if method in _INFERRED_ALIASES:
        return INFERRED
    return canonical_evidence_status("", review_status)
