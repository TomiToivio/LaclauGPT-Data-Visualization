"""Phase-1 temporal exploration over canonical relation data.

Temporal graph views are descriptive windows over explicit record clocks. Source,
collection and analysis time are never substituted for one another.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Literal

import pandas as pd

from .transforms import relations

TemporalClock = Literal["source", "collection", "analysis"]

_CLOCK_COLUMNS: dict[TemporalClock, str] = {
    "source": "source_timestamp",
    "collection": "collection_timestamp",
    "analysis": "analysis_timestamp",
}


def _utc_bound(value: object | None) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        raise ValueError(f"Invalid temporal boundary: {value!r}")
    return parsed


def _clock_series(frame: pd.DataFrame, clock: TemporalClock) -> pd.Series:
    column = _CLOCK_COLUMNS[clock]
    if column not in frame:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    return pd.to_datetime(frame[column], errors="coerce", utc=True)


def temporal_window(
    frame: pd.DataFrame,
    *,
    clock: TemporalClock = "source",
    start: object | None = None,
    end: object | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Return records inside an inclusive explicit-clock window.

    Records without the selected timestamp are excluded instead of being ordered by
    another clock. The returned metadata makes that exclusion inspectable.
    """
    if clock not in _CLOCK_COLUMNS:
        raise ValueError(f"Unsupported temporal clock: {clock!r}")

    start_ts = _utc_bound(start)
    end_ts = _utc_bound(end)
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise ValueError("Temporal window start must not be after end")

    values = _clock_series(frame, clock)
    explicit = values.notna()
    mask = explicit.copy()
    if start_ts is not None:
        mask &= values.ge(start_ts)
    if end_ts is not None:
        mask &= values.le(end_ts)

    selected = frame.loc[mask].copy()
    selected["_temporal_clock_value"] = values.loc[mask]
    sort_columns = ["_temporal_clock_value"]
    for column in ("source_url", "document_id"):
        if column in selected:
            sort_columns.append(column)
    selected = selected.sort_values(sort_columns, kind="mergesort").drop(
        columns=["_temporal_clock_value"]
    )

    metadata: dict[str, object] = {
        "clock": clock,
        "timestamp_field": _CLOCK_COLUMNS[clock],
        "start": start_ts.isoformat() if start_ts is not None else None,
        "end": end_ts.isoformat() if end_ts is not None else None,
        "records_total": int(len(frame)),
        "records_with_explicit_timestamp": int(explicit.sum()),
        "records_missing_timestamp": int((~explicit).sum()),
        "records_in_window": int(mask.sum()),
        "supported": bool(explicit.any()),
    }
    return selected, metadata


def _node_kinds(frame: pd.DataFrame) -> dict[str, set[str]]:
    kinds: dict[str, set[str]] = {}
    for _, row in frame.iterrows():
        actor = str(row.get("source_author") or "").strip()
        if actor:
            kinds.setdefault(actor, set()).add("actor")
        for field, kind in (
            ("entities", "entity"),
            ("signifiers", "signifier"),
            ("topics", "topic"),
            ("formations", "formation"),
        ):
            values = row.get(field, [])
            if not isinstance(values, list):
                continue
            for value in values:
                label = str(value).strip()
                if label:
                    kinds.setdefault(label, set()).add(kind)
    return kinds


def temporal_graph_projection(
    frame: pd.DataFrame,
    *,
    clock: TemporalClock = "source",
    start: object | None = None,
    end: object | None = None,
    max_edges: int = 500,
    max_nodes: int = 500,
) -> dict[str, object]:
    """Build a bounded deterministic graph for an explicit temporal window.

    The selected clock is record-level canonical data. Missing timestamps are omitted,
    never replaced with another clock. Edges retain source URLs, evidence references
    and the exact selected-clock timestamps that contributed to the aggregate.
    """
    if max_edges < 1 or max_nodes < 1:
        raise ValueError("Temporal graph limits must be positive")

    window, temporal = temporal_window(frame, clock=clock, start=start, end=end)
    if not temporal["supported"]:
        return {
            "nodes": [],
            "edges": [],
            "bounded": True,
            "truncated": False,
            "limits": {"nodes": max_nodes, "edges": max_edges},
            "temporal": temporal,
        }

    raw = relations(window)
    if raw.empty:
        return {
            "nodes": [],
            "edges": [],
            "bounded": True,
            "truncated": False,
            "limits": {"nodes": max_nodes, "edges": max_edges},
            "temporal": {**temporal, "relations_in_window": 0},
        }

    clock_column = _CLOCK_COLUMNS[clock]
    timestamps = _clock_series(window, clock)
    by_document: dict[str, str] = {}
    by_url: dict[str, str] = {}
    for idx, row in window.iterrows():
        value = timestamps.loc[idx]
        if pd.isna(value):
            continue
        stamp = value.isoformat()
        document_id = str(row.get("document_id") or "")
        source_url = str(row.get("source_url") or "")
        if document_id:
            by_document[document_id] = stamp
        if source_url:
            by_url[source_url] = stamp

    raw = raw.copy()
    raw["_clock_timestamp"] = [
        by_document.get(str(row.get("document_id") or ""))
        or by_url.get(str(row.get("source_url") or ""))
        or ""
        for row in raw.to_dict(orient="records")
    ]
    raw = raw[raw["_clock_timestamp"].ne("")].sort_values(
        [
            "_clock_timestamp",
            "source",
            "target",
            "type",
            "edge_status",
            "source_url",
            "document_id",
        ],
        kind="mergesort",
    )

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
                "clock": clock,
                "timestamp_field": clock_column,
                "timestamps": [],
            },
        )
        current["weight"] += float(edge["weight"])
        current["record_count"] += 1
        source_url = str(edge.get("source_url") or "")
        if source_url and source_url not in current["source_urls"]:
            current["source_urls"].append(source_url)
        for ref in edge.get("evidence_refs") or []:
            text = str(ref)
            if text and text not in current["evidence_refs"]:
                current["evidence_refs"].append(text)
        stamp = str(edge["_clock_timestamp"])
        if stamp not in current["timestamps"]:
            current["timestamps"].append(stamp)

    all_edges = list(grouped.values())
    for edge in all_edges:
        edge["timestamps"].sort()

    degree: Counter[str] = Counter()
    for edge in all_edges:
        degree[edge["source"]] += int(edge["record_count"])
        degree[edge["target"]] += int(edge["record_count"])

    ranked_nodes = [
        label
        for label, _count in sorted(
            degree.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    allowed_nodes = set(ranked_nodes[:max_nodes])
    edges = [
        edge
        for edge in all_edges
        if edge["source"] in allowed_nodes and edge["target"] in allowed_nodes
    ][:max_edges]

    # A degree-only node cut can split every relation when several nodes tie.
    # If the budget can represent an edge, deterministically seed the selected
    # node set from the strongest edge and then fill remaining slots by degree.
    if not edges and all_edges and max_nodes >= 2:
        seed_edge = sorted(
            all_edges,
            key=lambda edge: (
                -int(edge["record_count"]),
                -float(edge["weight"]),
                str(edge["source"]),
                str(edge["target"]),
                str(edge["type"]),
                str(edge["edge_status"]),
            ),
        )[0]
        seed_nodes = {str(seed_edge["source"]), str(seed_edge["target"])}
        if len(seed_nodes) <= max_nodes:
            allowed_nodes = set(seed_nodes)
            for label in ranked_nodes:
                if len(allowed_nodes) >= max_nodes:
                    break
                allowed_nodes.add(label)
            edges = [
                edge
                for edge in all_edges
                if edge["source"] in allowed_nodes and edge["target"] in allowed_nodes
            ][:max_edges]

    visible_degree: Counter[str] = Counter()
    for edge in edges:
        visible_degree[edge["source"]] += int(edge["record_count"])
        visible_degree[edge["target"]] += int(edge["record_count"])

    kinds = _node_kinds(window)
    nodes = [
        {
            "id": label,
            "label": label,
            "degree": int(count),
            "kinds": sorted(kinds.get(label, {"unknown"})),
        }
        for label, count in sorted(
            visible_degree.items(), key=lambda item: (-item[1], item[0])
        )
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "bounded": True,
        "truncated": len(degree) > max_nodes or len(all_edges) > max_edges,
        "limits": {"nodes": max_nodes, "edges": max_edges},
        "temporal": {
            **temporal,
            "relations_in_window": int(len(raw)),
            "aggregated_edges": int(len(all_edges)),
        },
    }
