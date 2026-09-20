"""Canonical Phase-1 Explore view models.

These transforms are storage- and UI-neutral. They preserve source identity and keep
source/collection/analysis/event clocks separate. They do not derive graph features.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .research_views import timeline_counts, timeline_events

DISTRIBUTION_FIELDS = ("formations", "topics", "entities", "signifiers")


def _labels(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [text for item in value if (text := str(item or "").strip())]


def label_distribution(frame: pd.DataFrame, field: str) -> pd.DataFrame:
    """Count a canonical multi-label field while retaining contributing source URLs."""
    columns = [field, "count", "source_urls"]
    if frame.empty or field not in frame:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, str]] = []
    for _, record in frame.iterrows():
        source_url = str(record.get("source_url") or "").strip()
        for label in _labels(record.get(field)):
            rows.append({field: label, "source_url": source_url})
    if not rows:
        return pd.DataFrame(columns=columns)

    source = pd.DataFrame(rows)
    grouped = (
        source.groupby(field, as_index=False)
        .agg(
            count=("source_url", "size"),
            source_urls=("source_url", lambda values: list(dict.fromkeys(v for v in values if v))),
        )
        .sort_values(["count", field], ascending=[False, True], kind="stable")
        .reset_index(drop=True)
    )
    return grouped[columns]


def formation_signifier_overlap(frame: pd.DataFrame) -> pd.DataFrame:
    """Return deterministic formation × signifier overlap without collapsing labels."""
    columns = ["formation", "signifier", "count", "source_urls"]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, str]] = []
    for _, record in frame.iterrows():
        source_url = str(record.get("source_url") or "").strip()
        for formation in _labels(record.get("formations")):
            for signifier in _labels(record.get("signifiers")):
                rows.append(
                    {
                        "formation": formation,
                        "signifier": signifier,
                        "source_url": source_url,
                    }
                )
    if not rows:
        return pd.DataFrame(columns=columns)

    source = pd.DataFrame(rows)
    grouped = (
        source.groupby(["formation", "signifier"], as_index=False)
        .agg(
            count=("source_url", "size"),
            source_urls=("source_url", lambda values: list(dict.fromkeys(v for v in values if v))),
        )
        .sort_values(
            ["count", "formation", "signifier"],
            ascending=[False, True, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    return grouped[columns]


def canonical_timeline(frame: pd.DataFrame, frequency: str = "D") -> pd.DataFrame:
    """Return canonical multi-clock counts plus the contributing source identities."""
    columns = ["period", "time_kind", "documents", "source_urls"]
    counts = timeline_counts(frame, frequency=frequency)
    if counts.empty:
        return pd.DataFrame(columns=columns)

    events = timeline_events(frame)
    events = events.assign(period=events["timestamp"].dt.floor(frequency))
    identities = (
        events.groupby(["period", "time_kind"], as_index=False)
        .agg(source_urls=("source_url", lambda values: list(dict.fromkeys(v for v in values if v))))
    )
    result = counts.merge(identities, on=["period", "time_kind"], how="left")
    result["source_urls"] = result["source_urls"].map(lambda value: value if isinstance(value, list) else [])
    return result[columns].sort_values(["period", "time_kind"], kind="stable").reset_index(drop=True)


def canonical_explore(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build the canonical Explore distributions, overlap table and multi-clock timeline."""
    views = {field: label_distribution(frame, field) for field in DISTRIBUTION_FIELDS}
    views["timeline"] = canonical_timeline(frame)
    views["formation_signifier"] = formation_signifier_overlap(frame)
    return views
