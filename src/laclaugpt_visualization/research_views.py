"""Storage-neutral helpers for map, timeline, reports and dashboard modes.

The functions in this module deliberately avoid Streamlit so they can be tested and
reused by CLI/notebook consumers. They consume the normalized visualization frame;
they never collect, geocode or analyze research material.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .statuses import canonical_coordinate_status

DASHBOARD_MODES = ("legacy_ep24", "canonical_live", "hybrid_research")


@dataclass(frozen=True)
class ResearchReport:
    report_id: str
    title: str
    date: pd.Timestamp | None
    body: str
    source_urls: tuple[str, ...] = ()
    path: str = ""


def infer_dashboard_mode(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "canonical_live"
    schema = frame["schema_version"].fillna("").astype(str) if "schema_version" in frame.columns else pd.Series(dtype=str)
    legacy_schema = schema.map(lambda value: value.strip().startswith("legacy-ep24-adapter-")).any()
    native_schema = schema.map(lambda value: bool(value.strip()) and not value.strip().startswith("legacy-ep24-adapter-")).any()
    legacy_payload = "legacy" in frame.columns and frame["legacy"].map(_is_nonempty).any()
    legacy_only_columns = (
        "lda_topic", "lda_minor_topics", "lda_topic_words",
        "manifestoberta_predicted_class", "manifestoberta_probabilities",
        "old_id", "puhti_filename",
    )
    legacy_only_values = any(column in frame.columns and frame[column].map(_is_nonempty).any() for column in legacy_only_columns)
    legacy_overlay = legacy_only_values or _different_populated_columns(frame, "whisper_transcript", "transcript") or _different_populated_columns(frame, "summary_analysis", "summary")
    has_legacy = bool(legacy_schema or legacy_payload or legacy_overlay)
    canonical_objects = any(column in frame.columns and frame[column].map(_is_nonempty).any() for column in ("formations", "signifiers", "relations", "evidence"))
    has_canonical = bool(native_schema or canonical_objects)
    if has_legacy and has_canonical:
        return "hybrid_research"
    if has_legacy:
        return "legacy_ep24"
    return "canonical_live"


def _different_populated_columns(frame: pd.DataFrame, legacy: str, canonical: str) -> bool:
    if legacy not in frame.columns or canonical not in frame.columns:
        return False
    for legacy_value, canonical_value in zip(frame[legacy], frame[canonical], strict=False):
        if _is_nonempty(legacy_value) and str(legacy_value).strip() != str(canonical_value or "").strip():
            return True
    return False


def _is_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return bool(str(value).strip())


def _first_present(row: Mapping[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in row and _is_nonempty(row[name]):
            return row[name]
    return None


def _to_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _coordinate_status(item: Mapping[str, Any], row: Mapping[str, Any]) -> str:
    return canonical_coordinate_status(item, row.get("review_status", ""))


def _location_candidates(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Read locations already present in canonical/analysis data; never geocode here."""
    candidates: list[Mapping[str, Any]] = []
    raw = row.get("raw_record")
    if isinstance(raw, Mapping):
        analysis = raw.get("analysis")
        if isinstance(analysis, Mapping):
            for key in ("locations", "location_entities", "events"):
                values = analysis.get(key)
                if isinstance(values, list):
                    candidates.extend(value for value in values if isinstance(value, Mapping))
        source = raw.get("source")
        if isinstance(source, Mapping):
            values = source.get("locations")
            if isinstance(values, list):
                candidates.extend(value for value in values if isinstance(value, Mapping))
    for key in ("locations", "location_entities", "events"):
        values = row.get(key)
        if isinstance(values, list):
            candidates.extend(value for value in values if isinstance(value, Mapping))
    # Legacy/single-location fallback.
    candidates.append(row)
    return candidates


def map_points(frame: pd.DataFrame) -> pd.DataFrame:
    """Extract one-or-many provenance-aware locations per source record.

    Coordinates must already exist in canonical/legacy data. Ambiguous/unresolved locations
    are omitted unless they have explicit valid coordinates; no network geocoder is called.
    """
    columns = [
        "source_url", "location_id", "label", "latitude", "longitude", "location",
        "event_type", "event_time", "coordinate_status", "coordinate_method",
        "ambiguity", "source_author", "summary", "evidence_refs", "provenance",
    ]
    rows: list[dict[str, Any]] = []
    for _, series in frame.iterrows():
        row = series.to_dict()
        seen: set[tuple[float, float, str]] = set()
        for index, item in enumerate(_location_candidates(row)):
            latitude = _to_number(_first_present(item, ("latitude", "lat", "event_lat")))
            longitude = _to_number(_first_present(item, ("longitude", "lng", "lon", "event_lng")))
            if latitude is None or longitude is None or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
            ambiguity = str(item.get("ambiguity") or item.get("geocode_ambiguity") or "").strip()
            resolved = item.get("resolved")
            if resolved is False and ambiguity:
                continue
            location = str(_first_present(item, ("name", "event_location", "location", "place", "label")) or "")
            dedup = (latitude, longitude, location)
            if dedup in seen:
                continue
            seen.add(dedup)
            evidence = item.get("evidence_refs") or item.get("evidence") or []
            if isinstance(evidence, str):
                evidence = [evidence]
            rows.append(
                {
                    "source_url": str(row.get("source_url", "")),
                    "location_id": str(item.get("location_id") or item.get("id") or f"loc-{index + 1}"),
                    "label": str(_first_present(item, ("event_name", "name", "label")) or row.get("source_author") or row.get("summary") or row.get("source_url", "")),
                    "latitude": latitude,
                    "longitude": longitude,
                    "location": location,
                    "event_type": str(_first_present(item, ("event_type", "kind", "type")) or row.get("source_type") or ""),
                    "event_time": _first_present(item, ("event_time", "event_date", "date", "timestamp")) or row.get("source_timestamp"),
                    "coordinate_status": _coordinate_status(item, row),
                    "coordinate_method": str(item.get("coordinate_method") or item.get("method") or item.get("origin") or ""),
                    "ambiguity": ambiguity,
                    "source_author": str(row.get("source_author") or ""),
                    "summary": str(row.get("human_readable_summary") or row.get("summary") or ""),
                    "evidence_refs": evidence if isinstance(evidence, list) else [],
                    "provenance": item.get("provenance") or row.get("provenance", []),
                }
            )
    result = pd.DataFrame(rows, columns=columns)
    if not result.empty:
        result["event_time"] = pd.to_datetime(result["event_time"], errors="coerce", utc=True)
    return result


def timeline_events(frame: pd.DataFrame) -> pd.DataFrame:
    """Return source-linked temporal observations with epistemically separate clocks."""
    columns = ["source_url", "time_kind", "timestamp", "label", "category", "summary", "evidence_refs", "review_status"]
    candidates = {
        "source": ("source_timestamp", "recording_datetime", "recording_date", "message_date"),
        "collection": ("collection_timestamp", "collected_at", "scraped_at"),
        "analysis": ("analysis_timestamp", "analyzed_at"),
        "event": ("event_time", "event_date"),
    }
    rows: list[dict[str, Any]] = []
    for _, record in frame.iterrows():
        source_url = str(record.get("source_url", ""))
        summary = str(record.get("human_readable_summary") or record.get("summary") or "")
        review_status = str(record.get("review_status") or "PROVISIONAL")
        for time_kind, names in candidates.items():
            value = _first_present(record, names)
            if value is None:
                continue
            timestamp = pd.to_datetime(value, errors="coerce", utc=True)
            if pd.isna(timestamp):
                continue
            rows.append({
                "source_url": source_url,
                "time_kind": time_kind,
                "timestamp": timestamp,
                "label": summary or str(record.get("source_author") or source_url),
                "category": "record",
                "summary": summary,
                "evidence_refs": [],
                "review_status": review_status,
            })
        raw = record.get("raw_record")
        analysis = raw.get("analysis", {}) if isinstance(raw, Mapping) else {}
        events = analysis.get("events", []) if isinstance(analysis, Mapping) else []
        if isinstance(events, list):
            for item in events:
                if not isinstance(item, Mapping):
                    continue
                timestamp = pd.to_datetime(_first_present(item, ("event_time", "event_date", "date", "timestamp")), errors="coerce", utc=True)
                if pd.isna(timestamp):
                    continue
                evidence = item.get("evidence_refs") or item.get("evidence") or []
                if isinstance(evidence, str):
                    evidence = [evidence]
                rows.append({
                    "source_url": source_url,
                    "time_kind": "event",
                    "timestamp": timestamp,
                    "label": str(item.get("event_name") or item.get("name") or item.get("label") or summary or source_url),
                    "category": str(item.get("event_type") or item.get("kind") or "extracted_event"),
                    "summary": str(item.get("description") or summary),
                    "evidence_refs": evidence if isinstance(evidence, list) else [],
                    "review_status": str(item.get("validation_status") or review_status),
                })
    return pd.DataFrame(rows, columns=columns)


def timeline_counts(frame: pd.DataFrame, frequency: str = "D") -> pd.DataFrame:
    events = timeline_events(frame)
    if events.empty:
        return pd.DataFrame(columns=["period", "time_kind", "documents"])
    events = events.assign(period=events["timestamp"].dt.floor(frequency))
    return events.groupby(["period", "time_kind"])["source_url"].nunique().reset_index(name="documents").sort_values(["period", "time_kind"])


def discourse_timeline(frame: pd.DataFrame, frequency: str = "D") -> pd.DataFrame:
    """Long-form actor/entity/signifier/topic/formation appearances over source time."""
    columns = ["period", "dimension", "label", "count", "source_urls"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    dimensions = {
        "actor": "source_author",
        "entity": "entities",
        "signifier": "signifiers",
        "topic": "topics",
        "formation": "formations",
    }
    for _, row in frame.iterrows():
        timestamp = pd.to_datetime(row.get("source_timestamp"), errors="coerce", utc=True)
        if pd.isna(timestamp):
            continue
        period = timestamp.floor(frequency)
        for dimension, field in dimensions.items():
            value = row.get(field)
            values = value if isinstance(value, list) else [value]
            for item in values:
                label = str(item or "").strip()
                if label:
                    rows.append({"period": period, "dimension": dimension, "label": label, "source_url": str(row.get("source_url", ""))})
    if not rows:
        return pd.DataFrame(columns=columns)
    source = pd.DataFrame(rows)
    grouped = source.groupby(["period", "dimension", "label"], as_index=False).agg(count=("source_url", "size"), source_urls=("source_url", lambda values: list(dict.fromkeys(values))))
    return grouped[columns]


def _parse_report_json(path: Path) -> ResearchReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"report JSON must contain an object: {path}")
    body = payload.get("markdown") or payload.get("body") or payload.get("summary") or ""
    raw_urls = payload.get("source_urls") or payload.get("sources") or []
    if isinstance(raw_urls, str):
        raw_urls = [raw_urls]
    date = pd.to_datetime(payload.get("date") or path.stem, errors="coerce", utc=True)
    return ResearchReport(str(payload.get("report_id") or path.stem), str(payload.get("title") or path.stem), None if pd.isna(date) else date, str(body), tuple(str(value) for value in raw_urls if str(value).strip()), str(path))


def _parse_report_markdown(path: Path) -> ResearchReport:
    text = path.read_text(encoding="utf-8")
    title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")), path.stem)
    date = pd.to_datetime(path.stem, errors="coerce", utc=True)
    return ResearchReport(path.stem, title, None if pd.isna(date) else date, text, path=str(path))


def load_reports(root: str | Path | None) -> list[ResearchReport]:
    if root is None:
        return []
    path = Path(root)
    if not path.exists() or not path.is_dir():
        return []
    reports: list[ResearchReport] = []
    for candidate in sorted(path.iterdir()):
        if candidate.suffix.lower() == ".md":
            reports.append(_parse_report_markdown(candidate))
        elif candidate.suffix.lower() == ".json":
            try:
                reports.append(_parse_report_json(candidate))
            except (json.JSONDecodeError, TypeError):
                continue
    return sorted(reports, key=lambda report: (report.date is not None, report.date or pd.Timestamp.min.tz_localize("UTC")), reverse=True)
