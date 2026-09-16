"""Storage-neutral helpers for map, timeline, reports and dashboard modes.

The functions in this module deliberately avoid Streamlit so they can be tested and
reused by CLI/notebook consumers.  They consume the normalized visualization frame;
they never collect or analyze research material.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

DASHBOARD_MODES = ("legacy_ep24", "canonical_live", "hybrid_research")


@dataclass(frozen=True)
class ResearchReport:
    """A generated report that remains linked to its backing records when possible."""

    report_id: str
    title: str
    date: pd.Timestamp | None
    body: str
    source_urls: tuple[str, ...] = ()
    path: str = ""


def infer_dashboard_mode(frame: pd.DataFrame) -> str:
    """Choose a useful default without changing the underlying data."""
    if frame.empty:
        return "canonical_live"
    legacy_markers = {
        "new_id",
        "whisper_transcript",
        "summary_analysis",
        "formula_of_populism_analysis",
        "lda_topic",
    }
    has_legacy = bool(legacy_markers.intersection(frame.columns)) and any(
        frame[column].notna().any()
        for column in legacy_markers.intersection(frame.columns)
    )
    has_canonical = any(
        column in frame.columns and frame[column].map(_is_nonempty).any()
        for column in ("formations", "signifiers", "relations", "evidence", "provenance")
    )
    if has_legacy and has_canonical:
        return "hybrid_research"
    if has_legacy:
        return "legacy_ep24"
    return "canonical_live"


def _is_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return bool(str(value).strip())


def _first_present(row: pd.Series, names: Iterable[str]) -> Any:
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


def map_points(frame: pd.DataFrame) -> pd.DataFrame:
    """Extract valid geospatial observations without inventing coordinates.

    Supports generic canonical-ish fields plus historical event_lat/event_lng aliases.
    Invalid/out-of-range values are discarded and source identity is preserved.
    """
    columns = [
        "source_url",
        "label",
        "latitude",
        "longitude",
        "location",
        "event_type",
        "event_time",
        "provenance",
    ]
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        latitude = _to_number(_first_present(row, ("latitude", "lat", "event_lat")))
        longitude = _to_number(_first_present(row, ("longitude", "lng", "lon", "event_lng")))
        if latitude is None or longitude is None:
            continue
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue
        rows.append(
            {
                "source_url": str(row.get("source_url", "")),
                "label": str(
                    _first_present(row, ("event_name", "location_name", "source_author", "summary"))
                    or row.get("source_url", "")
                ),
                "latitude": latitude,
                "longitude": longitude,
                "location": str(_first_present(row, ("event_location", "location", "place")) or ""),
                "event_type": str(_first_present(row, ("event_type", "source_type")) or ""),
                "event_time": _first_present(row, ("event_time", "event_date", "source_timestamp")),
                "provenance": row.get("provenance", []),
            }
        )
    result = pd.DataFrame(rows, columns=columns)
    if not result.empty:
        result["event_time"] = pd.to_datetime(result["event_time"], errors="coerce", utc=True)
    return result


def timeline_events(frame: pd.DataFrame) -> pd.DataFrame:
    """Return long-form timestamps while keeping epistemically different clocks separate."""
    candidates = {
        "source": ("source_timestamp", "recording_datetime", "recording_date", "message_date"),
        "collection": ("collection_timestamp", "collected_at", "scraped_at"),
        "analysis": ("analysis_timestamp", "analyzed_at"),
        "event": ("event_time", "event_date"),
    }
    rows: list[dict[str, Any]] = []
    for _, record in frame.iterrows():
        for time_kind, names in candidates.items():
            value = _first_present(record, names)
            if value is None:
                continue
            timestamp = pd.to_datetime(value, errors="coerce", utc=True)
            if pd.isna(timestamp):
                continue
            rows.append(
                {
                    "source_url": str(record.get("source_url", "")),
                    "time_kind": time_kind,
                    "timestamp": timestamp,
                    "label": str(record.get("summary") or record.get("source_author") or record.get("source_url", "")),
                }
            )
    return pd.DataFrame(rows, columns=["source_url", "time_kind", "timestamp", "label"])


def timeline_counts(frame: pd.DataFrame, frequency: str = "D") -> pd.DataFrame:
    events = timeline_events(frame)
    if events.empty:
        return pd.DataFrame(columns=["period", "time_kind", "documents"])
    events = events.assign(period=events["timestamp"].dt.floor(frequency))
    return (
        events.groupby(["period", "time_kind"])["source_url"]
        .nunique()
        .reset_index(name="documents")
        .sort_values(["period", "time_kind"])
    )


def _parse_report_json(path: Path) -> ResearchReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"report JSON must contain an object: {path}")
    body = payload.get("markdown") or payload.get("body") or payload.get("summary") or ""
    raw_urls = payload.get("source_urls") or payload.get("sources") or []
    if isinstance(raw_urls, str):
        raw_urls = [raw_urls]
    date = pd.to_datetime(payload.get("date") or path.stem, errors="coerce", utc=True)
    return ResearchReport(
        report_id=str(payload.get("report_id") or path.stem),
        title=str(payload.get("title") or path.stem),
        date=None if pd.isna(date) else date,
        body=str(body),
        source_urls=tuple(str(value) for value in raw_urls if str(value).strip()),
        path=str(path),
    )


def _parse_report_markdown(path: Path) -> ResearchReport:
    text = path.read_text(encoding="utf-8")
    title = next(
        (line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")),
        path.stem,
    )
    date = pd.to_datetime(path.stem, errors="coerce", utc=True)
    return ResearchReport(
        report_id=path.stem,
        title=title,
        date=None if pd.isna(date) else date,
        body=text,
        path=str(path),
    )


def load_reports(root: str | Path | None) -> list[ResearchReport]:
    """Load local generated reports without assuming a project-specific storage backend."""
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
    return sorted(
        reports,
        key=lambda report: (report.date is not None, report.date or pd.Timestamp.min.tz_localize("UTC")),
        reverse=True,
    )
