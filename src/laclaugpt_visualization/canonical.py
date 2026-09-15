"""Canonical Collection/Analysis record adapter for visualization.

Visualization consumes the public canonical contract and flattens only the fields
needed by researcher-facing view models. It never imports Analysis internals.
"""
from __future__ import annotations

from typing import Any


def _labels(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    labels: list[str] = []
    for value in values:
        if isinstance(value, dict):
            label = value.get("label") or value.get("name") or value.get("text")
            if label:
                labels.append(str(label))
        elif value is not None and str(value).strip():
            labels.append(str(value))
    return labels


def _text_items(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        if isinstance(value, dict):
            text = value.get("text") or value.get("description") or value.get("quote")
            if text:
                result.append(str(text))
        elif value is not None and str(value).strip():
            result.append(str(value))
    return result


def flatten_canonical(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten one canonical record into the stable visualization view model."""
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    content = record.get("content") if isinstance(record.get("content"), dict) else {}
    analysis = record.get("analysis") if isinstance(record.get("analysis"), dict) else {}
    review = record.get("review") if isinstance(record.get("review"), dict) else {}
    provenance = record.get("provenance") if isinstance(record.get("provenance"), list) else []

    transcripts = content.get("transcripts", [])
    transcript = "\n".join(_text_items(transcripts)) or str(content.get("text") or "")
    ocr = _text_items(content.get("ocr", []))
    frames = content.get("frames", []) if isinstance(content.get("frames"), list) else []
    media = (
        content.get("media_references", [])
        if isinstance(content.get("media_references"), list)
        else []
    )

    source_url = str(record.get("source_url") or "")
    analysis_timestamp = analysis.get("completed_at") or analysis.get("started_at") or ""
    if not analysis_timestamp and provenance:
        last = provenance[-1]
        if isinstance(last, dict):
            analysis_timestamp = last.get("created_at") or ""

    return {
        "schema_version": str(record.get("schema_version") or ""),
        "document_id": source_url,
        "source_url": source_url,
        "source_platform": str(source.get("platform") or ""),
        "source_author": str(source.get("author") or ""),
        "source_country": str(source.get("country") or ""),
        "source_language": str(source.get("language") or content.get("language") or ""),
        "source_timestamp": source.get("created_at") or source.get("collected_at") or "",
        "analysis_timestamp": analysis_timestamp,
        "analysis_status": str(analysis.get("status") or "collection-only"),
        "summary": str(analysis.get("summary") or ""),
        "transcript": transcript,
        "translated_text": str(content.get("translated_text") or ""),
        "ocr": ocr,
        "frames": frames,
        "media_references": media,
        "entities": _labels(analysis.get("entities", [])),
        "topics": _labels(analysis.get("topics", [])),
        "formations": _labels(analysis.get("formations", [])),
        "signifiers": _labels(analysis.get("signifiers", [])),
        "nodal_points": _labels(analysis.get("nodal_points", [])),
        "discourses": _labels(analysis.get("discourses", [])),
        "imaginaries": _labels(analysis.get("imaginaries", [])),
        "frontier": _labels(analysis.get("frontier", [])),
        "affects": _labels(analysis.get("affects", [])),
        "sentiment_labels": _labels(analysis.get("sentiments", [])),
        "relations": analysis.get("relations", []) if isinstance(analysis.get("relations"), list) else [],
        "uncertainties": [str(value) for value in analysis.get("uncertainty", [])],
        "abstentions": [str(value) for value in analysis.get("abstentions", [])],
        "model_runs": analysis.get("model_runs", []) if isinstance(analysis.get("model_runs"), list) else [],
        "review_status": str(review.get("status") or "PROVISIONAL"),
        "review": review,
        "provenance": provenance,
        "raw_record": record,
    }
