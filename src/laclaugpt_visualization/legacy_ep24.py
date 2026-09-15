"""Lossless compatibility adapter for historical EP24 flat exports.

Legacy rows remain fully inspectable while the rest of Visualization consumes the common
view model. Canonical source identity is always ``source_url``; legacy IDs remain aliases.
"""
from __future__ import annotations

import json
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


def _collect_numbered(record: dict[str, Any], prefix: str) -> list[str]:
    values: list[str] = []
    for index in range(1, 7):
        value = record.get(f"{prefix}_{index}")
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
    """Map EP24 fields into the common view while retaining every original column."""
    legacy_id = str(_first(record, "new_id", "video_id", "old_id", "id"))
    source_url = str(_first(record, "source_url", "url", "video_url")) or f"legacy:ep24:{legacy_id}"
    transcript = str(_first(record, "whisper_transcript", "transcript"))
    translated = str(_first(record, "whisper_translated", "translated_text"))
    ocr = _collect_numbered(record, "ocr")
    frame_analysis = [
        str(_first(record, f"frame_{index}", f"frame_analysis_{index}"))
        for index in range(1, 7)
        if _first(record, f"frame_{index}", f"frame_analysis_{index}")
    ]
    entities = _split(_first(record, "new_entity", "entities", "NER_entities", "spacy_entities"))
    topics = _split(_first(record, "new_theme", "topics", "political_themes"))
    sentiment = []
    for label in ("positive", "neutral", "negative"):
        value = record.get(label)
        if value is not None and str(value).strip() and str(value).strip() not in {"0", "0.0"}:
            sentiment.append(label)

    source_native_ids = {
        key: str(record[key])
        for key in ("new_id", "video_id", "old_id", "id")
        if record.get(key) is not None and str(record.get(key)).strip()
    }
    summary = str(_first(record, "summary_analysis", "analysis_summary", "summary"))
    human_markdown = (
        "# Legacy EP24 researcher record\n\n"
        f"## Source\n{source_url}\n\n"
        f"## Whisper transcript\n{transcript or 'n/a'}\n\n"
        f"## OCR\n{' | '.join(ocr) or 'n/a'}\n\n"
        f"## Frame analysis\n{' | '.join(frame_analysis) or 'n/a'}\n\n"
        f"## Analysis summary\n{summary or 'n/a'}\n\n"
        "## Original legacy row\n```json\n"
        f"{json.dumps(record, ensure_ascii=False, indent=2, default=str)}\n```\n"
    )

    result: dict[str, Any] = {
        "schema_version": "legacy-ep24-adapter-2",
        "document_id": source_url,
        "source_url": source_url,
        "source_native_ids": source_native_ids,
        "raw_capture": {
            "ref": "",
            "payload": dict(record),
            "metadata": {"preservation": "legacy-dataframe-row"},
        },
        "source_platform": str(_first(record, "source_type", "platform")),
        "source_type": str(_first(record, "source_type")),
        "source_author": str(_first(record, "author_username", "profile_name", "author")),
        "source_author_fullname": str(_first(record, "author_fullname")),
        "source_country": str(_first(record, "country")),
        "source_language": str(_first(record, "whisper_language", "language")),
        "source_timestamp": _first(record, "recording_datetime", "recording_date", "corrected_date", "date", "timestamp"),
        "collection_timestamp": _first(record, "collection_timestamp", "scraped_at"),
        "collector": str(_first(record, "collector", "collector_id")),
        "collection_method": str(_first(record, "collection_method")),
        "raw_ref": str(_first(record, "raw_ref")),
        "raw_payload": dict(record),
        "raw_metadata": {},
        "intermediate": {
            "asr": [{"id": "transcript_1", "text": transcript, "language": _first(record, "whisper_language"), "translated_text": translated}] if transcript else [],
            "ocr": [{"id": f"ocr_{index}", "text": value} for index, value in enumerate(ocr, start=1)],
            "frames": [],
            "frame_analysis": [{"id": f"frame_{index}", "description": value} for index, value in enumerate(frame_analysis, start=1)],
            "translations": ([{"id": "translation_1", "text": translated}] if translated else []),
            "stage_outputs": {},
        },
        "analysis_timestamp": _first(record, "analysis_timestamp"),
        "analysis_status": "analyzed" if summary else "collection-only",
        "summary": summary,
        "human_readable_summary": summary,
        "human_readable_markdown": human_markdown,
        "source_text": str(_first(record, "text", "caption", "description")),
        "transcript": transcript,
        "translated_text": translated,
        "ocr": ocr,
        "frames": _collect_numbered(record, "frames"),
        "frame_analysis": frame_analysis,
        "media_references": [
            value
            for value in (_first(record, "video_file", "video_filename", "allas_filename", "puhti_filename"),)
            if value
        ],
        "file_references": [],
        "entities": entities,
        "entity_mentions": [],
        "topics": topics,
        "topic_assignments": [],
        "classifications": [],
        "embeddings": [],
        "formations": _split(_first(record, "formation", "ideological_formation")),
        "signifiers": _split(_first(record, "signifiers", "nodal_points")),
        "nodal_points": _split(_first(record, "nodal_points")),
        "discourses": _split(_first(record, "discourses")),
        "imaginaries": _split(_first(record, "imaginaries")),
        "us": _split(_first(record, "formula_of_populism_us_elements", "formula_of_populism_us")),
        "them": [],
        "frontier": _split(_first(record, "formula_of_populism_frontier_elements", "formula_of_populism_frontier")),
        "affects": _split(_first(record, "formula_of_populism_us_affects", "formula_of_populism_frontier_affects")),
        "sentiment_labels": sentiment,
        "formula_of_populism": record.get("formula_of_populism_analysis"),
        "relations": [],
        "uncertainties": [],
        "abstentions": [],
        "codebook_refs": [],
        "memory_refs": [],
        "model_runs": [],
        "evidence": [],
        "review_status": str(_first(record, "review_status")) or "PROVISIONAL",
        "review": {},
        "legacy": dict(record),
        "provenance": [{"method": "legacy_ep24_adapter", "schema": "legacy-ep24-adapter-2"}],
        "raw_record": dict(record),
    }

    # Keep the most important old dashboard columns at top-level in addition to modern fields.
    for key, value in record.items():
        if key not in result:
            result[key] = value
    result["whisper_transcript"] = transcript
    result["whisper_language"] = str(_first(record, "whisper_language"))
    result["whisper_translated"] = translated
    result["summary_analysis"] = summary
    for index in range(1, 7):
        result[f"ocr_{index}"] = str(record.get(f"ocr_{index}") or "")
        result[f"frame_{index}"] = str(_first(record, f"frame_{index}", f"frame_analysis_{index}"))
    return result
