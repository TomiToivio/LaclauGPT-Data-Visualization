"""Pure monitor/explore view-model transformations.

All outputs are descriptive summaries. They do not establish theoretical validity.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from .data import explode_labels


def monitor(frame: pd.DataFrame) -> dict[str, object]:
    source_time = pd.to_datetime(frame.get("source_timestamp"), errors="coerce", utc=True)
    analysis_time = pd.to_datetime(frame.get("analysis_timestamp"), errors="coerce", utc=True)
    status = frame.get("analysis_status", pd.Series("collection-only", index=frame.index))
    reviewed = frame.get("review_status", pd.Series("PROVISIONAL", index=frame.index))
    return {
        "documents": len(frame),
        "analyzed": int((status != "collection-only").sum()),
        "awaiting_analysis": int((status == "collection-only").sum()),
        "awaiting_review": int((~reviewed.isin(["ACCEPTED", "CANONICAL", "verified"])).sum()),
        "latest_source": source_time.max().isoformat() if len(source_time) and pd.notna(source_time.max()) else "",
        "latest_analysis": analysis_time.max().isoformat() if len(analysis_time) and pd.notna(analysis_time.max()) else "",
        "formations": explode_labels(frame, "formations"),
        "signifiers": explode_labels(frame, "signifiers"),
        "actors": _scalar_counts(frame, "source_author"),
    }


def _scalar_counts(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if column not in frame:
        return pd.DataFrame(columns=[column, "count"])
    values = frame[column].fillna("").astype(str)
    values = values[values.str.strip().ne("")]
    return values.value_counts().rename_axis(column).reset_index(name="count")


def timeline(frame: pd.DataFrame, *, freq: str = "D") -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["period", "documents"])
    values = pd.to_datetime(frame["source_timestamp"], errors="coerce", utc=True).dropna()
    if values.empty:
        return pd.DataFrame(columns=["period", "documents"])
    return values.dt.floor(freq).value_counts().sort_index().rename_axis("period").reset_index(name="documents")


def _edge_status(relation: dict[str, Any], review_status: str) -> str:
    explicit = str(
        relation.get("validation_status")
        or relation.get("status")
        or relation.get("provenance_type")
        or relation.get("origin")
        or ""
    ).strip().casefold()
    if explicit in {"human", "validated", "human-validated", "verified", "accepted", "canonical"}:
        return "human-validated"
    if review_status.upper() in {"ACCEPTED", "CANONICAL", "REVISED"}:
        return "human-reviewed-record"
    if explicit in {"inferred", "generated", "llm", "model"}:
        return "inferred"
    if explicit in {"observed", "extracted", "source"}:
        return "extracted"
    return "unrecorded"


def relations(frame: pd.DataFrame) -> pd.DataFrame:
    """Return source-linked relation rows with provenance/validation semantics."""
    columns = [
        "source", "target", "type", "document_id", "source_url", "weight",
        "edge_status", "evidence_refs", "summary", "timestamp",
    ]
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        values = row.get("relations", [])
        if not isinstance(values, list):
            continue
        for relation in values:
            if not isinstance(relation, dict):
                continue
            rows.append(
                {
                    "source": relation.get("source") or relation.get("from") or relation.get("source_id") or "",
                    "target": relation.get("target") or relation.get("to") or relation.get("target_id") or "",
                    "type": relation.get("type") or relation.get("relation") or relation.get("label") or "",
                    "document_id": row.get("document_id", ""),
                    "source_url": row.get("source_url", ""),
                    "weight": relation.get("weight", relation.get("confidence", "")),
                    "edge_status": _edge_status(relation, str(row.get("review_status", ""))),
                    "evidence_refs": relation.get("evidence_refs") or relation.get("evidence") or [],
                    "summary": relation.get("summary") or relation.get("description") or "",
                    "timestamp": relation.get("timestamp") or relation.get("created_at") or "",
                }
            )
    return pd.DataFrame(rows, columns=columns)


def explore(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "formations": explode_labels(frame, "formations"),
        "signifiers": explode_labels(frame, "signifiers"),
        "topics": explode_labels(frame, "topics"),
        "entities": explode_labels(frame, "entities"),
        "discourses": explode_labels(frame, "discourses"),
        "imaginaries": explode_labels(frame, "imaginaries"),
    }


def cooccurrence(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    counts: Counter[tuple[str, str]] = Counter()
    if column not in frame:
        return pd.DataFrame(columns=["source", "target", "count"])
    for values in frame[column]:
        if not isinstance(values, list):
            continue
        labels = sorted({str(value).strip() for value in values if str(value).strip()})
        for index, source in enumerate(labels):
            for target in labels[index + 1 :]:
                counts[(source, target)] += 1
    return pd.DataFrame(
        [{"source": source, "target": target, "count": count} for (source, target), count in counts.items()]
    )
