"""Bounded compatibility adapter for historical EP24 flat exports.

Legacy names stop here. The rest of the visualization package consumes the
common view model produced by :func:`adapt`.
"""
from __future__ import annotations

from typing import Any

_EP24_MARKERS = {
    "new_id",
    "video_id",
    "whisper_transcript",
    "summary_analysis",
    "formula_of_populism_analysis",
    "allas_filename",
}


def looks_like_ep24(record: dict[str, Any]) -> bool:
    return bool(_EP24_MARKERS.intersection(record))


def _first(record: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = record.get(name)
        if value is not None and str(value).strip():
            return value
    return ""


def _collect_prefix(record: dict[str, Any], prefix: str) -> list[str]:
    values: list[str] = []
    for key in sorted(record):
        if key == prefix or key.startswith(f"{prefix}_"):
            value = record.get(key)
            if value is not None and str(value).strip():
                values.append(str(value))
    return values


def _split(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    separator = ";" if ";" in text else ","
    return [part.strip() for part in text.split(separator) if part.strip()]


def adapt(record: dict[str, Any]) -> dict[str, Any]:
    """Map useful EP24 fields into the canonical visualization view model."""
    document_id = str(_first(record, "new_id", "video_id", "old_id", "id"))
    source_url = str(_first(record, "source_url", "url", "video_url")) or f"legacy:ep24:{document_id}"
    transcript = str(_first(record, "whisper_transcript", "transcript"))
    translated = str(_first(record, "whisper_translated", "translated_text"))
    entities = _split(_first(record, "new_entity", "entities", "NER_entities", "spacy_entities"))
    topics = _split(_first(record, "new_theme", "topics", "political_themes"))
    sentiment = []
    for label in ("positive", "neutral", "negative"):
        value = record.get(label)
        if value is not None and str(value).strip() and str(value).strip() not in {"0", "0.0"}:
            sentiment.append(label)

    return {
        "schema_version": "legacy-ep24-adapter-1",
        "document_id": document_id or source_url,
        "source_url": source_url,
        "source_platform": str(_first(record, "source_type", "platform")),
        "source_author": str(_first(record, "author_username", "profile_name", "author")),
        "source_country": str(_first(record, "country")),
        "source_language": str(_first(record, "whisper_language", "language")),
        "source_timestamp": _first(
            record, "recording_datetime", "recording_date", "corrected_date", "date", "timestamp"
        ),
        "analysis_timestamp": _first(record, "analysis_timestamp"),
        "analysis_status": "analyzed" if _first(record, "summary_analysis", "summary") else "collection-only",
        "summary": str(_first(record, "summary_analysis", "analysis_summary", "summary")),
        "transcript": transcript,
        "translated_text": translated,
        "ocr": _collect_prefix(record, "ocr"),
        "frames": _collect_prefix(record, "frame"),
        "media_references": [
            value
            for value in (
                _first(record, "video_file", "video_filename", "allas_filename", "puhti_filename"),
            )
            if value
        ],
        "entities": entities,
        "topics": topics,
        "formations": _split(_first(record, "formation", "ideological_formation")),
        "signifiers": _split(_first(record, "signifiers", "nodal_points")),
        "nodal_points": _split(_first(record, "nodal_points")),
        "discourses": _split(_first(record, "discourses")),
        "imaginaries": _split(_first(record, "imaginaries")),
        "frontier": _split(
            _first(record, "formula_of_populism_frontier_elements", "formula_of_populism_frontier")
        ),
        "affects": _split(
            _first(record, "formula_of_populism_us_affects", "formula_of_populism_frontier_affects")
        ),
        "sentiment_labels": sentiment,
        "relations": [],
        "uncertainties": [],
        "abstentions": [],
        "review_status": str(_first(record, "review_status")) or "PROVISIONAL",
        "legacy": {
            "political_preference": record.get("political_preference"),
            "lda_topic": record.get("lda_topic"),
            "lda_topic_words": record.get("lda_topic_words"),
            "formula_of_populism_analysis": record.get("formula_of_populism_analysis"),
        },
        "provenance": [{"method": "legacy_ep24_adapter", "schema": "legacy-ep24-adapter-1"}],
        "raw_record": record,
    }
