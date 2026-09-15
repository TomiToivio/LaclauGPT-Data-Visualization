"""Canonical Collection/Analysis record adapter for visualization.

Visualization consumes the project-wide canonical contract and flattens records
only after reconstructing the canonical nested representation.  It never imports
Analysis or Collection implementation internals and never treats a DataFrame as
persistent schema.
"""
from __future__ import annotations

import json
import math
from typing import Any

_OBJECT_FIELDS = ("source_native_ids", "source", "content", "evidence", "analysis", "review")
_LIST_FIELDS = ("provenance",)


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _decode_json(value: Any, expected: type) -> Any:
    """Decode deterministic JSON used by flat/SQL adapters.

    CSV and some SQLite layouts serialize canonical objects/lists as JSON text.
    Python repr is deliberately not parsed: the canonical contract requires JSON.
    """
    if isinstance(value, expected):
        return value
    if _missing(value) or value == "":
        return expected()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return expected()
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return expected()
        return decoded if isinstance(decoded, expected) else expected()
    return expected()


def reconstruct_canonical(record: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct canonical nested sections from a backend-neutral row/document."""
    result = dict(record)
    if not result.get("source_url") and result.get("source_uri"):
        result["source_url"] = result["source_uri"]
    for field in _OBJECT_FIELDS:
        result[field] = _decode_json(result.get(field), dict)
    for field in _LIST_FIELDS:
        result[field] = _decode_json(result.get(field), list)
    return result


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
    """Flatten one canonical record into a stable, non-persistent view model."""
    record = reconstruct_canonical(record)
    source = record["source"]
    content = record["content"]
    evidence = record["evidence"]
    analysis = record["analysis"]
    review = record["review"]
    provenance = record["provenance"]

    transcripts = content.get("transcripts", [])
    transcript = "\n".join(_text_items(transcripts)) or str(content.get("text") or "")
    ocr = _text_items(content.get("ocr", []))
    frames = content.get("frames", []) if isinstance(content.get("frames"), list) else []
    media = content.get("media_references", []) if isinstance(content.get("media_references"), list) else []
    files = content.get("file_references", []) if isinstance(content.get("file_references"), list) else []

    source_url = str(record.get("source_url") or "")
    analysis_timestamp = analysis.get("completed_at") or analysis.get("started_at") or ""
    if not analysis_timestamp and provenance:
        last = provenance[-1]
        if isinstance(last, dict):
            analysis_timestamp = last.get("created_at") or ""

    return {
        "schema_version": str(record.get("schema_version") or ""),
        # document_id is a compatibility/display alias only. Canonical identity is source_url.
        "document_id": source_url,
        "source_url": source_url,
        "source_native_ids": record.get("source_native_ids", {}),
        "source_platform": str(source.get("platform") or ""),
        "source_type": str(source.get("source_type") or ""),
        "source_author": str(source.get("author") or ""),
        "source_author_fullname": str(source.get("author_fullname") or ""),
        "source_country": str(source.get("country") or ""),
        "source_language": str(source.get("language") or content.get("language") or ""),
        "source_timestamp": source.get("created_at") or "",
        "collection_timestamp": source.get("collected_at") or "",
        "collector": str(source.get("collector") or ""),
        "collection_method": str(source.get("collection_method") or ""),
        "raw_ref": source.get("raw_ref"),
        "raw_metadata": source.get("raw_metadata", {}),
        "analysis_timestamp": analysis_timestamp,
        "analysis_status": str(analysis.get("status") or "collection-only"),
        "summary": str(analysis.get("summary") or ""),
        "source_text": str(content.get("text") or ""),
        "transcript": transcript,
        "translated_text": str(content.get("translated_text") or ""),
        "ocr": ocr,
        "frames": frames,
        "media_references": media,
        "file_references": files,
        "entities": _labels(analysis.get("entities", [])),
        "entity_mentions": analysis.get("entity_mentions", []) if isinstance(analysis.get("entity_mentions"), list) else [],
        "topics": _labels(analysis.get("topics", [])),
        "classifications": analysis.get("classifications", []) if isinstance(analysis.get("classifications"), list) else [],
        "formations": _labels(analysis.get("formations", [])),
        "signifiers": _labels(analysis.get("signifiers", [])),
        "nodal_points": _labels(analysis.get("nodal_points", [])),
        "discourses": _labels(analysis.get("discourses", [])),
        "imaginaries": _labels(analysis.get("imaginaries", [])),
        "us": _labels(analysis.get("us", [])),
        "them": _labels(analysis.get("them", [])),
        "frontier": _labels(analysis.get("frontier", [])),
        "affects": _labels(analysis.get("affects", [])),
        "sentiment_labels": _labels(analysis.get("sentiments", [])),
        "formula_of_populism": analysis.get("formula_of_populism"),
        "relations": analysis.get("relations", []) if isinstance(analysis.get("relations"), list) else [],
        "uncertainties": [str(value) for value in analysis.get("uncertainty", [])],
        "abstentions": [str(value) for value in analysis.get("abstentions", [])],
        "model_runs": analysis.get("model_runs", []) if isinstance(analysis.get("model_runs"), list) else [],
        "evidence": evidence,
        "review_status": str(review.get("status") or "PROVISIONAL"),
        "review": review,
        "provenance": provenance,
        "raw_record": record,
    }
