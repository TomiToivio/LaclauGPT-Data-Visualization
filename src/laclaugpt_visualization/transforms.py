"""Pure monitor/explore view-model transformations.

All outputs are descriptive summaries. They do not establish theoretical validity.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from .data import explode_labels


def monitor(frame: pd.DataFrame) -> dict[str, object]:
    """Build compact descriptive corpus metrics from already-present view fields."""
    source_time = pd.to_datetime(frame.get("source_timestamp"), errors="coerce", utc=True)
    analysis_time = pd.to_datetime(frame.get("analysis_timestamp"), errors="coerce", utc=True)
    status = (
        frame.get("analysis_status", pd.Series("collection-only", index=frame.index))
        .fillna("collection-only")
        .astype(str)
        .str.strip()
        .str.casefold()
    )
    analyzed = status.isin({"analyzed", "complete", "completed", "ok", "success"})
    errors = status.isin({"error", "failed", "failure"})
    reviewed = frame.get("review_status", pd.Series("PROVISIONAL", index=frame.index))
    return {
        "documents": len(frame),
        "analyzed": int(analyzed.sum()),
        "awaiting_analysis": int((~analyzed & ~errors).sum()),
        "errors": int(errors.sum()),
        "awaiting_review": int((~reviewed.isin(["ACCEPTED", "CANONICAL", "verified"])).sum()),
        "latest_source": source_time.max().isoformat() if len(source_time) and pd.notna(source_time.max()) else "",
        "latest_analysis": analysis_time.max().isoformat() if len(analysis_time) and pd.notna(analysis_time.max()) else "",
        "formations": explode_labels(frame, "formations"),
        "signifiers": explode_labels(frame, "signifiers"),
        "actors": _scalar_counts(frame, "source_author"),
        "frequency_note": (
            "Actor, formation and signifier frequencies are descriptive occurrence counts only; "
            "they do not establish hegemony, nodal status, ideology identity or theoretical validity."
        ),
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


def _relation_weight(value: Any) -> float:
    """Normalize an optional descriptive relation weight without failing the graph view."""
    try:
        return float(value if value not in (None, "") else 1.0)
    except (TypeError, ValueError):
        return 1.0


def relations(frame: pd.DataFrame) -> pd.DataFrame:
    """Return source-linked relation rows with provenance/validation semantics."""
    columns = [
        "source", "target", "type", "document_id", "source_url", "weight",
        "edge_status", "evidence_refs", "summary", "timestamp",
        "source_timestamp", "collection_timestamp", "analysis_timestamp",
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
                    "weight": _relation_weight(relation.get("weight")),
                    "edge_status": _edge_status(relation, str(row.get("review_status", "PROVISIONAL"))),
                    "evidence_refs": evidence,
                    "summary": str(row.get("human_readable_summary") or row.get("summary") or ""),
                    "timestamp": row.get("source_timestamp") or row.get("analysis_timestamp") or "",
                    "source_timestamp": row.get("source_timestamp") or "",
                    "collection_timestamp": row.get("collection_timestamp") or "",
                    "analysis_timestamp": row.get("analysis_timestamp") or "",
                }
            )
    return pd.DataFrame(rows, columns=columns)


def relation_summary(frame: pd.DataFrame) -> pd.DataFrame:
    values = relations(frame)
    if values.empty:
        return pd.DataFrame(columns=["type", "count"])
    return values["type"].value_counts().rename_axis("type").reset_index(name="count")


def graph_projection(
    frame: pd.DataFrame,
    *,
    max_edges: int = 500,
    max_nodes: int = 500,
) -> dict[str, object]:
    """Build a bounded canonical-data network fallback.

    Edges remain linked to source records/evidence. Duplicate relations are aggregated only
    for weight/degree while preserving contributing record URLs. Both node and edge counts are
    bounded so a dashboard cannot accidentally materialize a complete corpus graph.
    """
    node_limit = max(0, int(max_nodes))
    edge_limit = max(0, int(max_edges))
    raw = relations(frame)
    if raw.empty or node_limit == 0 or edge_limit == 0:
        return {
            "nodes": [],
            "edges": [],
            "bounded": True,
            "truncated": not raw.empty,
            "limits": {"nodes": node_limit, "edges": edge_limit},
        }

    raw_relation_count = len(raw)
    raw = raw.head(edge_limit).copy()
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
                "source_timestamps": [],
                "collection_timestamps": [],
                "analysis_timestamps": [],
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
        for field, target in (
            ("source_timestamp", "source_timestamps"),
            ("collection_timestamp", "collection_timestamps"),
            ("analysis_timestamp", "analysis_timestamps"),
        ):
            timestamp = str(edge.get(field) or "").strip()
            if timestamp and timestamp not in current[target]:
                current[target].append(timestamp)

    all_edges = list(grouped.values())
    degree: Counter[str] = Counter()
    for edge in all_edges:
        degree[edge["source"]] += edge["record_count"]
        degree[edge["target"]] += edge["record_count"]

    allowed_nodes = {
        label for label, _count in degree.most_common(node_limit)
    }
    edges = [
        edge
        for edge in all_edges
        if edge["source"] in allowed_nodes and edge["target"] in allowed_nodes
    ][:edge_limit]

    node_types: dict[str, set[str]] = {}
    for _, row in frame.iterrows():
        actor = str(row.get("source_author") or "").strip()
        if actor:
            node_types.setdefault(actor, set()).add("actor")
        for field, kind in (
            ("entities", "entity"),
            ("signifiers", "signifier"),
            ("topics", "topic"),
            ("formations", "formation"),
        ):
            values = row.get(field, [])
            if isinstance(values, list):
                for value in values:
                    text = str(value).strip()
                    if text:
                        node_types.setdefault(text, set()).add(kind)

    nodes = [
        {
            "id": label,
            "label": label,
            "degree": int(count),
            "kinds": sorted(node_types.get(label, {"unknown"})),
        }
        for label, count in degree.most_common(node_limit)
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "bounded": True,
        "truncated": (
            raw_relation_count > edge_limit
            or len(degree) > node_limit
            or len(all_edges) > edge_limit
        ),
        "limits": {"nodes": node_limit, "edges": edge_limit},
    }


_TEMPORAL_CLOCKS = {
    "source": "source_timestamp",
    "collection": "collection_timestamp",
    "analysis": "analysis_timestamp",
}


def _utc_boundary(value: object, *, label: str) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {label} timestamp: {value!r}") from exc
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def temporal_graph_projection(
    frame: pd.DataFrame,
    *,
    clock: str,
    start: object = None,
    end: object = None,
    max_edges: int = 500,
    max_nodes: int = 500,
) -> dict[str, object]:
    """Build a bounded graph for one explicit canonical clock and inclusive window.

    No fallback between source, collection and analysis clocks is allowed. Records with a
    missing timestamp for the selected clock are excluded and reported in metadata.
    """
    if clock not in _TEMPORAL_CLOCKS:
        allowed = ", ".join(sorted(_TEMPORAL_CLOCKS))
        raise ValueError(f"clock must be one of: {allowed}")

    start_ts = _utc_boundary(start, label="start")
    end_ts = _utc_boundary(end, label="end")
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise ValueError("start timestamp must not be after end timestamp")

    column = _TEMPORAL_CLOCKS[clock]
    if column in frame:
        timestamps = pd.to_datetime(frame[column], errors="coerce", utc=True)
    else:
        timestamps = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")

    mask = timestamps.notna()
    if start_ts is not None:
        mask &= timestamps >= start_ts
    if end_ts is not None:
        mask &= timestamps <= end_ts

    selected = frame.loc[mask].copy()
    if not selected.empty:
        selected["_temporal_timestamp"] = timestamps.loc[selected.index]
        sort_columns = ["_temporal_timestamp"]
        for candidate in ("source_url", "document_id"):
            if candidate in selected:
                sort_columns.append(candidate)
        selected = selected.sort_values(sort_columns, kind="stable").drop(
            columns=["_temporal_timestamp"]
        )

    projection = graph_projection(
        selected,
        max_edges=max_edges,
        max_nodes=max_nodes,
    )
    projection["temporal"] = {
        "clock": clock,
        "timestamp_column": column,
        "start": start_ts.isoformat() if start_ts is not None else "",
        "end": end_ts.isoformat() if end_ts is not None else "",
        "records_in_window": int(mask.sum()),
        "records_missing_timestamp": int(timestamps.isna().sum()),
        "inclusive_boundaries": True,
    }
    return projection


def explore(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "timeline": timeline(frame),
        "formations": explode_labels(frame, "formations"),
        "topics": explode_labels(frame, "topics"),
        "entities": explode_labels(frame, "entities"),
        "signifiers": explode_labels(frame, "signifiers"),
        "relations": relation_summary(frame),
    }
