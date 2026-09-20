"""Read-only view models for upstream Discourse Network Analysis artifacts.

Visualization consumes the DNA section of laclaugpt.multimethod.v1. It does not
derive projections, communities, or analytical classifications.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

DNA_ARTIFACT_SCHEMA = "laclaugpt.multimethod.v1"
DNA_PROJECTIONS = (
    "actor_congruence",
    "actor_conflict",
    "concept_congruence",
    "concept_conflict",
)
DEFAULT_ROW_LIMIT = 500
MAX_ROW_LIMIT = 5000


@dataclass(frozen=True, slots=True)
class DnaCapability:
    available: bool
    reason: str
    statement_count: int = 0
    projection_count: int = 0


def load_dna_artifact(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("DNA artifact must be a JSON object")
    if payload.get("schema") != DNA_ARTIFACT_SCHEMA:
        raise ValueError(f"expected {DNA_ARTIFACT_SCHEMA}")
    return payload


def dna_capability(artifact: Mapping[str, Any]) -> DnaCapability:
    if artifact.get("schema") != DNA_ARTIFACT_SCHEMA:
        return DnaCapability(False, f"expected {DNA_ARTIFACT_SCHEMA}")
    statements = artifact.get("statements")
    dna = artifact.get("dna")
    if not isinstance(statements, list):
        return DnaCapability(False, "upstream statements contract is missing")
    if not isinstance(dna, Mapping):
        return DnaCapability(False, "upstream DNA output is missing")
    required_statement_fields = {"statement_id", "actor_id", "concept_id", "source_url"}
    for row in statements:
        if not isinstance(row, Mapping):
            return DnaCapability(False, "upstream statement row is not an object")
        if not required_statement_fields.issubset(row):
            return DnaCapability(False, "upstream DNA statements do not preserve evidence identity")
    available_projections = sum(bool(dna.get(name)) for name in DNA_PROJECTIONS)
    return DnaCapability(
        True,
        "stable upstream DNA contract available",
        statement_count=len(statements),
        projection_count=available_projections,
    )


def statements_frame(artifact: Mapping[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame(artifact.get("statements") or [])
    if not frame.empty and "timestamp" in frame:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    return frame


def actor_concept_statement_edges(
    artifact: Mapping[str, Any],
    *,
    include_abstained: bool = False,
    limit: int = DEFAULT_ROW_LIMIT,
) -> pd.DataFrame:
    frame = statements_frame(artifact)
    columns = [
        "statement_id",
        "actor_id",
        "actor_name",
        "concept_id",
        "concept_label",
        "stance",
        "source_url",
        "source_record_id",
        "confidence",
        "validation_status",
        "abstained",
        "evidence",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    if not include_abstained and "abstained" in frame:
        frame = frame[~frame["abstained"].fillna(False).astype(bool)]
    for column in columns:
        if column not in frame:
            frame[column] = None
    return frame[columns].head(_bounded_limit(limit)).copy()


def projection_edges(
    artifact: Mapping[str, Any],
    projection: str,
    *,
    minimum_weight: float = 0.0,
    limit: int = DEFAULT_ROW_LIMIT,
) -> pd.DataFrame:
    if projection not in DNA_PROJECTIONS:
        raise ValueError(f"unsupported DNA projection: {projection}")
    dna = artifact.get("dna") or {}
    frame = pd.DataFrame(dna.get(projection) or [])
    if frame.empty:
        return frame
    weight_col = next((name for name in ("weight", "count", "score") if name in frame), None)
    if weight_col is not None and minimum_weight > 0:
        numeric = pd.to_numeric(frame[weight_col], errors="coerce").fillna(0)
        frame = frame[numeric >= minimum_weight]
    return frame.head(_bounded_limit(limit)).copy()


def evidence_for_statement(
    artifact: Mapping[str, Any],
    statement_id: str,
) -> pd.DataFrame:
    frame = statements_frame(artifact)
    if frame.empty or "statement_id" not in frame:
        return pd.DataFrame()
    selected = frame[frame["statement_id"].astype(str) == str(statement_id)].copy()
    preferred = [
        "statement_id",
        "source_url",
        "source_record_id",
        "actor_id",
        "actor_name",
        "concept_id",
        "concept_label",
        "stance",
        "proposition",
        "evidence",
        "confidence",
        "validation_status",
        "abstained",
    ]
    return selected[[column for column in preferred if column in selected]]


def dna_coverage(artifact: Mapping[str, Any]) -> Mapping[str, Any]:
    dna = artifact.get("dna") or {}
    coverage = dna.get("coverage") or {}
    return coverage if isinstance(coverage, Mapping) else {}


def _bounded_limit(limit: int) -> int:
    return max(1, min(int(limit), MAX_ROW_LIMIT))
