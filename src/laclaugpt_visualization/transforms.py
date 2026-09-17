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
            source = str(relation.get("source_ref") or relation.get("source") or "").strip()
            target = str(relation.get("target_ref") or relation.get("target") or "").strip()
            if not source or not target:
                continue
            evidence = relation.get("evidence_refs") or relation.get("evidence") or []
            if isinstance(evidence, str):
                evidence = [evidence]
            if not isinstance(evidence, list):
                evidence = []
            rows.append(
                {
                    "source": source,
                    "target": target,
                    "type": str(relation.get("relation_type") or relation.get("type") or "related_to"),
                    "document_id": str(row.get("document_id", "")),
                    "source_url": str(row.get("source_url", "")),
                    "weight": float(relation.get("weight") or 1.0),
                    "edge_status": _edge_status(relation, str(row.get("review_status", "PROVISIONAL"))),
                    "evidence_refs": evidence,
                    "summary": str(row.get("human_readable_summary") or row.get("summary") or ""),
                    "timestamp": row.get("source_timestamp") or row.get("analysis_timestamp") or "",
                }
            )
    return pd.DataFrame(rows, columns=columns)


def relation_summary(frame: pd.DataFrame) -> pd.DataFrame:
    values = relations(frame)
    if values.empty:
        return pd.DataFrame(columns=["type", "count"])
    return values["type"].value_counts().rename_axis("type").reset_index(name="count")


def graph_projection(frame: pd.DataFrame, *, max_edges: int = 500) -> dict[str, list[dict[str, object]]]:
    """Build a bounded canonical-data network fallback.

    Edges remain linked to source records/evidence. Duplicate relations are aggregated only
    for weight/degree while preserving contributing record URLs.
    """
    raw = relations(frame)
    if raw.empty:
        return {"nodes": [], "edges": []}

    raw = raw.head(max(1, max_edges)).copy()
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for edge in raw.to_dict(orient="records"):
        key = (edge["source"], edge["target"], edge["type"], edge["edge_status"])
        current = grouped.setdefault(
            key,
            {
                "source": edge["source"],
                "target": edge["target"],
                "type": edge["type"],
                "edge_status": edge["edge_status"],
                "weight": 0.0,
                "record_count": 0,
                "source_urls": [],
                "evidence_refs": [],
            },
        )
        current["weight"] += float(edge["weight"])
        current["record_count"] += 1
        if edge["source_url"] and edge["source_url"] not in current["source_urls"]:
            current["source_urls"].append(edge["source_url"])
        for ref in edge["evidence_refs"]:
            text = str(ref)
            if text and text not in current["evidence_refs"]:
                current["evidence_refs"].append(text)

    edges = list(grouped.values())
    degree: Counter[str] = Counter()
    for edge in edges:
        degree[edge["source"]] += edge["record_count"]
        degree[edge["target"]] += edge["record_count"]

    node_types: dict[str, set[str]] = {}
    for _, row in frame.iterrows():
        actor = str(row.get("source_author") or "").strip()
        if actor:
            node_types.setdefault(actor, set()).add("actor")
        for field, kind in (("entities", "entity"), ("signifiers", "signifier"), ("topics", "topic"), ("formations", "formation")):
            values = row.get(field, [])
            if isinstance(values, list):
                for value in values:
                    text = str(value).strip()
                    if text:
                        node_types.setdefault(text, set()).add(kind)

    nodes = [
        {"id": label, "label": label, "degree": int(count), "kinds": sorted(node_types.get(label, {"unknown"}))}
        for label, count in degree.most_common()
    ]
    return {"nodes": nodes, "edges": edges}


def explore(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "timeline": timeline(frame),
        "formations": explode_labels(frame, "formations"),
        "topics": explode_labels(frame, "topics"),
        "entities": explode_labels(frame, "entities"),
        "signifiers": explode_labels(frame, "signifiers"),
        "relations": relation_summary(frame),
    }
