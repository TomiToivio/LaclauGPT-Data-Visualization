"""Pure monitor/explore view-model transformations.

All outputs are descriptive summaries. They do not establish theoretical validity.
"""
from __future__ import annotations

import pandas as pd

from .data import explode_labels
from .query_backends import GraphRequest, graph_from_frame


def monitor(frame: pd.DataFrame) -> dict[str, object]:
    source_time = pd.to_datetime(frame.get("source_timestamp"), errors="coerce", utc=True)
    analysis_time = pd.to_datetime(frame.get("analysis_timestamp"), errors="coerce", utc=True)
    status = frame.get("analysis_status", pd.Series("collection-only", index=frame.index))
    reviewed = frame.get("review_status", pd.Series("PROVISIONAL", index=frame.index))
    return {
        "documents": len(frame),
        "analyzed": int((status != "collection-only").sum()),
        "awaiting_analysis": int((status == "collection-only").sum()),
        "awaiting_review": int(~reviewed.isin(["ACCEPTED", "CANONICAL", "verified"]).sum()),
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


def relations(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for _, row in frame.iterrows():
        values = row.get("relations", [])
        if not isinstance(values, list):
            continue
        for relation in values:
            if not isinstance(relation, dict):
                continue
            rows.append(
                {
                    "source": str(relation.get("source_ref") or relation.get("source") or ""),
                    "target": str(relation.get("target_ref") or relation.get("target") or ""),
                    "type": str(relation.get("relation_type") or relation.get("type") or ""),
                    "document_id": str(row.get("document_id", "")),
                }
            )
    return pd.DataFrame(rows, columns=["source", "target", "type", "document_id"])


def relation_summary(frame: pd.DataFrame) -> pd.DataFrame:
    values = relations(frame)
    if values.empty:
        return pd.DataFrame(columns=["type", "count"])
    return values["type"].value_counts().rename_axis("type").reset_index(name="count")


def graph_projection(
    frame: pd.DataFrame,
    *,
    max_nodes: int = 500,
    max_edges: int = 1000,
) -> dict[str, object]:
    """Return a bounded, provenance-preserving graph projection for ordinary UI views."""
    payload, _evidence = graph_from_frame(
        frame,
        GraphRequest(max_nodes=max_nodes, max_edges=max_edges),
    )
    return payload


def explore(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "timeline": timeline(frame),
        "formations": explode_labels(frame, "formations"),
        "topics": explode_labels(frame, "topics"),
        "entities": explode_labels(frame, "entities"),
        "signifiers": explode_labels(frame, "signifiers"),
        "relations": relation_summary(frame),
    }
