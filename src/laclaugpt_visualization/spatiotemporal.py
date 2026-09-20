"""Phase-1 spatiotemporal view models.

This module is intentionally isolated from legacy map/timeline helpers.  It consumes
already-normalized canonical visualization records and never geocodes, guesses, or
substitutes missing temporal/geographic evidence.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


_TIMELINE_COLUMNS = (
    "source_url",
    "time_kind",
    "timestamp",
    "label",
    "category",
    "evidence_refs",
    "review_status",
)

_MAP_COLUMNS = (
    "source_url",
    "location_id",
    "label",
    "latitude",
    "longitude",
    "location",
    "event_type",
    "event_time",
    "coordinate_status",
    "coordinate_method",
    "evidence_refs",
)


def _as_evidence_refs(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _timestamp(value: Any) -> pd.Timestamp | None:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(parsed) else parsed


def _analysis_mapping(record: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = record.get("raw_record")
    if not isinstance(raw, Mapping):
        return {}
    analysis = raw.get("analysis")
    return analysis if isinstance(analysis, Mapping) else {}


def spatiotemporal_timeline(frame: pd.DataFrame) -> pd.DataFrame:
    """Return explicit clocks without substituting one timestamp for another.

    Source, collection, and analysis clocks are read only from their canonical fields.
    Extracted event time is included only when the event itself carries a valid explicit
    timestamp and evidence references. Missing times remain missing.
    """

    rows: list[dict[str, Any]] = []
    for _, series in frame.iterrows():
        record = series.to_dict()
        source_url = str(record.get("source_url") or "")
        label = str(
            record.get("human_readable_summary")
            or record.get("summary")
            or record.get("source_author")
            or source_url
        )
        review_status = str(record.get("review_status") or "PROVISIONAL")

        for kind, field in (
            ("source", "source_timestamp"),
            ("collection", "collection_timestamp"),
            ("analysis", "analysis_timestamp"),
        ):
            timestamp = _timestamp(record.get(field))
            if timestamp is None:
                continue
            rows.append(
                {
                    "source_url": source_url,
                    "time_kind": kind,
                    "timestamp": timestamp,
                    "label": label,
                    "category": "record",
                    "evidence_refs": [],
                    "review_status": review_status,
                }
            )

        events = _analysis_mapping(record).get("events")
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, Mapping):
                continue
            explicit_time = next(
                (
                    event.get(field)
                    for field in ("event_time", "event_date", "date", "timestamp")
                    if event.get(field) not in (None, "")
                ),
                None,
            )
            timestamp = _timestamp(explicit_time)
            evidence_refs = _as_evidence_refs(
                event.get("evidence_refs") or event.get("evidence")
            )
            if timestamp is None or not evidence_refs:
                continue
            rows.append(
                {
                    "source_url": source_url,
                    "time_kind": "event",
                    "timestamp": timestamp,
                    "label": str(
                        event.get("event_name")
                        or event.get("name")
                        or event.get("label")
                        or label
                    ),
                    "category": str(
                        event.get("event_type")
                        or event.get("kind")
                        or "extracted_event"
                    ),
                    "evidence_refs": evidence_refs,
                    "review_status": str(
                        event.get("validation_status") or review_status
                    ),
                }
            )

    result = pd.DataFrame(rows, columns=_TIMELINE_COLUMNS)
    if result.empty:
        return result
    return result.sort_values(
        ["timestamp", "time_kind", "source_url", "label"], kind="stable"
    ).reset_index(drop=True)


def spatiotemporal_timeline_counts(
    frame: pd.DataFrame, frequency: str = "D"
) -> pd.DataFrame:
    events = spatiotemporal_timeline(frame)
    if events.empty:
        return pd.DataFrame(columns=["period", "time_kind", "documents"])
    counted = events.assign(period=events["timestamp"].dt.floor(frequency))
    return (
        counted.groupby(["period", "time_kind"], as_index=False)["source_url"]
        .nunique()
        .rename(columns={"source_url": "documents"})
        .sort_values(["period", "time_kind"], kind="stable")
        .reset_index(drop=True)
    )


def _location_status(item: Mapping[str, Any]) -> tuple[str, str]:
    status = str(
        item.get("coordinate_status")
        or item.get("validation_status")
        or item.get("status")
        or ""
    ).strip().casefold()
    method = str(
        item.get("coordinate_method") or item.get("method") or item.get("origin") or ""
    ).strip().casefold()

    if status in {
        "validated",
        "human-validated",
        "verified",
        "accepted",
        "canonical",
    } or bool(item.get("human_validated")):
        return "human-validated", method
    if method in {"source", "source-provided", "native", "metadata"}:
        return "source-provided", method
    return "", method


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def spatiotemporal_map_points(frame: pd.DataFrame) -> pd.DataFrame:
    """Return only explicit, evidence-backed geographic points.

    No geocoder is called. Inferred/geocoded/unrecorded coordinates are disabled unless
    the location is explicitly human-validated and evidence-linked. Coordinates missing
    either axis, outside legal bounds, unresolved/ambiguous, or lacking evidence are
    omitted rather than repaired.
    """

    rows: list[dict[str, Any]] = []
    for _, series in frame.iterrows():
        record = series.to_dict()
        source_url = str(record.get("source_url") or "")
        analysis = _analysis_mapping(record)
        candidates: list[Mapping[str, Any]] = []

        raw = record.get("raw_record")
        if isinstance(raw, Mapping):
            source = raw.get("source")
            if isinstance(source, Mapping) and isinstance(source.get("locations"), list):
                candidates.extend(
                    item
                    for item in source["locations"]
                    if isinstance(item, Mapping)
                )

        for key in ("locations", "location_entities", "events"):
            values = analysis.get(key)
            if isinstance(values, list):
                candidates.extend(
                    item for item in values if isinstance(item, Mapping)
                )

        seen: set[tuple[float, float, str]] = set()
        for index, item in enumerate(candidates):
            latitude = _number(item.get("latitude", item.get("lat")))
            longitude = _number(
                item.get("longitude", item.get("lng", item.get("lon")))
            )
            if (
                latitude is None
                or longitude is None
                or not -90 <= latitude <= 90
                or not -180 <= longitude <= 180
            ):
                continue
            if item.get("resolved") is False:
                continue

            status, method = _location_status(item)
            evidence_refs = _as_evidence_refs(
                item.get("evidence_refs") or item.get("evidence")
            )
            if not status or not evidence_refs:
                continue

            location = str(
                item.get("name")
                or item.get("location")
                or item.get("place")
                or item.get("label")
                or ""
            )
            key = (latitude, longitude, location)
            if key in seen:
                continue
            seen.add(key)

            rows.append(
                {
                    "source_url": source_url,
                    "location_id": str(
                        item.get("location_id") or item.get("id") or f"loc-{index + 1}"
                    ),
                    "label": str(
                        item.get("event_name")
                        or item.get("name")
                        or item.get("label")
                        or record.get("source_author")
                        or source_url
                    ),
                    "latitude": latitude,
                    "longitude": longitude,
                    "location": location,
                    "event_type": str(
                        item.get("event_type") or item.get("kind") or item.get("type") or ""
                    ),
                    "event_time": _timestamp(
                        next(
                            (
                                item.get(field)
                                for field in ("event_time", "event_date", "date", "timestamp")
                                if item.get(field) not in (None, "")
                            ),
                            None,
                        )
                    ),
                    "coordinate_status": status,
                    "coordinate_method": method,
                    "evidence_refs": evidence_refs,
                }
            )

    result = pd.DataFrame(rows, columns=_MAP_COLUMNS)
    if result.empty:
        return result
    return result.sort_values(
        ["source_url", "location_id", "latitude", "longitude"], kind="stable"
    ).reset_index(drop=True)
