"""Canonical Collection/Analysis record adapter for visualization.

Visualization reconstructs the nested research record first, then exposes both the new
view model and the stable EP24-era researcher aliases. DataFrames and dashboard columns
are projections, never the persistent schema.
"""
from __future__ import annotations

import json
import math
from typing import Any

_OBJECT_FIELDS = (
    "source_native_ids",
    "raw_capture",
    "source",
    "content",
    "intermediate",
    "analysis",
    "human_readable",
    "review",
    "legacy",
)
_LIST_FIELDS = ("source_units", "alignments", "evidence", "provenance")

LEGACY_COLUMNS = (
    "country", "author_username", "account_type", "source_type", "source_recording",
    "video_filename", "video_file", "frames", "whisper_transcript", "whisper_language",
    "whisper_translated", "ocr_1", "ocr_2", "ocr_3", "ocr_4", "ocr_5", "ocr_6",
    "frame_1", "frame_2", "frame_3", "frame_4", "frame_5", "frame_6",
    "summary_analysis", "entities_legacy", "topics_legacy", "spacy_entities", "positive",
    "neutral", "negative", "us_and_them", "us_legacy", "them_legacy", "social_contract",
    "social_contract_topics", "NER_entities", "NER_politicians", "NER_political_parties",
    "political_themes", "formula_of_populism_analysis", "formula_of_populism_us",
    "formula_of_populism_frontier", "recording_date", "day_number", "video_id",
    "sequence_number", "recording_datetime", "profile_name", "allas_filename", "lda_topic",
    "lda_minor_topics", "lda_topic_words", "political_preference",
    "manifestoberta_predicted_class", "manifestoberta_probabilities", "corrected_date",
    "original_date", "corresponding_date", "split_number", "new_entity", "new_theme",
    "video_duration", "new_id", "old_id", "puhti_filename", "raw_ref",
    "raw_payload_json", "human_readable_summary", "human_readable_markdown",
)


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _decode_json(value: Any, expected: type) -> Any:
    """Decode deterministic JSON used by flat/SQL adapters."""
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
    """Reconstruct nested sections and tolerate 1.0 records during migration."""
    result = dict(record)
    if not result.get("source_url") and result.get("source_uri"):
        result["source_url"] = result["source_uri"]
    for field in _OBJECT_FIELDS:
        result[field] = _decode_json(result.get(field), dict)
    for field in _LIST_FIELDS:
        result[field] = _decode_json(result.get(field), list)
    source = result["source"]
    if not result["raw_capture"]:
        result["raw_capture"] = {
            "ref": source.get("raw_ref"),
            "payload": None,
            "metadata": {"preservation": "legacy-record"},
        }
    result["intermediate"].setdefault("asr", [])
    result["intermediate"].setdefault("ocr", [])
    result["intermediate"].setdefault("frames", [])
    result["intermediate"].setdefault("frame_analysis", [])
    result["intermediate"].setdefault("translations", [])
    result["intermediate"].setdefault("stage_outputs", {})
    result["human_readable"].setdefault("summary", "")
    result["human_readable"].setdefault("markdown", "")
    return result


def _labels(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    labels: list[str] = []
    for value in values:
        if isinstance(value, dict):
            label = value.get("label") or value.get("canonical_label") or value.get("name") or value.get("text")
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


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _legacy_scalar(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def flatten_canonical(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten canonical data while retaining old dashboard/dataframe field names."""
    record = reconstruct_canonical(record)
    raw_capture = record["raw_capture"]
    source = record["source"]
    content = record["content"]
    intermediate = record["intermediate"]
    evidence = record["evidence"]
    analysis = record["analysis"]
    human = record["human_readable"]
    review = record["review"]
    provenance = record["provenance"]
    legacy = dict(record["legacy"])

    transcripts = _list(content.get("transcripts"))
    transcript = "\n".join(_text_items(transcripts)) or str(content.get("text") or "")
    whisper_language = next(
        (str(item.get("language")) for item in transcripts if isinstance(item, dict) and item.get("language")),
        "",
    )
    whisper_translated = "\n".join(
        str(item.get("translated_text"))
        for item in transcripts
        if isinstance(item, dict) and item.get("translated_text")
    ) or str(content.get("translated_text") or "")

    ocr_rows = _list(intermediate.get("ocr")) or _list(content.get("ocr"))
    ocr = _text_items(ocr_rows)
    frames = _list(intermediate.get("frames")) or _list(content.get("frames"))
    frame_analysis_rows = _list(intermediate.get("frame_analysis"))
    if not frame_analysis_rows:
        frame_analysis_rows = [
            item for item in frames if isinstance(item, dict) and item.get("description")
        ]
    frame_analysis = _text_items(frame_analysis_rows)
    media = _list(content.get("media_references"))
    files = _list(content.get("file_references"))

    source_url = str(record.get("source_url") or "")
    analysis_timestamp = analysis.get("completed_at") or analysis.get("started_at") or ""
    if not analysis_timestamp and provenance:
        last = provenance[-1]
        if isinstance(last, dict):
            analysis_timestamp = last.get("created_at") or ""

    entities = _labels(analysis.get("entities", []))
    topics = _labels(analysis.get("topics", []))
    sentiments = _labels(analysis.get("sentiments", []))
    formula = analysis.get("formula_of_populism")
    native_ids = record.get("source_native_ids", {})
    object_ref = next(
        (
            str(item.get("object_ref") or item.get("ref"))
            for item in media
            if isinstance(item, dict) and (item.get("object_ref") or item.get("ref"))
        ),
        "",
    )

    result: dict[str, Any] = {
        "schema_version": str(record.get("schema_version") or ""),
        "fixture_version": str(record.get("fixture_version") or ""),
        "document_id": source_url,
        "source_url": source_url,
        "source_native_ids": native_ids,
        "source_units": record["source_units"],
        "alignments": record["alignments"],
        "raw_capture": raw_capture,
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
        "raw_ref": raw_capture.get("ref") or source.get("raw_ref") or "",
        "raw_payload": raw_capture.get("payload"),
        "raw_metadata": source.get("raw_metadata", {}),
        "intermediate": intermediate,
        "analysis_timestamp": analysis_timestamp,
        "analysis_status": str(analysis.get("status") or "collection-only"),
        "summary": str(analysis.get("summary") or ""),
        "human_readable_summary": str(human.get("summary") or ""),
        "human_readable_markdown": str(human.get("markdown") or ""),
        "source_text": str(content.get("text") or ""),
        "content_title": str(content.get("title") or ""),
        "transcript": transcript,
        "translated_text": whisper_translated,
        "ocr": ocr,
        "ocr_items": ocr_rows,
        "frames": frames,
        "frame_analysis": frame_analysis,
        "media_references": media,
        "file_references": files,
        "representations": _list(analysis.get("representations")),
        "analysis_objects": _list(analysis.get("analysis_objects")),
        "entities": entities,
        "entity_mentions": _list(analysis.get("entity_mentions")),
        "topics": topics,
        "topic_assignments": _list(analysis.get("topic_assignments")),
        "classifications": _list(analysis.get("classifications")),
        "embeddings": _list(analysis.get("embeddings")),
        "formations": _labels(analysis.get("formations", [])),
        "signifiers": _labels(analysis.get("signifiers", [])),
        "nodal_points": _labels(analysis.get("nodal_points", [])),
        "discourses": _labels(analysis.get("discourses", [])),
        "imaginaries": _labels(analysis.get("imaginaries", [])),
        "us": _labels(analysis.get("us", [])),
        "them": _labels(analysis.get("them", [])),
        "frontier": _labels(analysis.get("frontier", [])),
        "affects": _labels(analysis.get("affects", [])),
        "sentiment_labels": sentiments,
        "formula_of_populism": formula,
        "relations": _list(analysis.get("relations")),
        "uncertainties": _list(analysis.get("uncertainty")),
        "abstentions": _list(analysis.get("abstentions")),
        "codebook_refs": _list(analysis.get("codebook_refs")),
        "memory_refs": _list(analysis.get("memory_refs")),
        "model_runs": _list(analysis.get("model_runs")),
        "evidence": evidence,
        "review_status": str(review.get("status") or "PROVISIONAL"),
        "review": review,
        "provenance": provenance,
        "legacy": legacy,
        "raw_record": record,
    }

    # Old dataframe/dashboard aliases. Imported historical values survive when no newer
    # canonical equivalent is present.
    aliases: dict[str, Any] = dict(legacy)
    canonical_aliases = {
        "country": result["source_country"],
        "author_username": result["source_author"],
        "source_type": result["source_type"] or result["source_platform"],
        "video_filename": native_ids.get("video_filename", ""),
        "video_file": object_ref,
        "whisper_transcript": transcript,
        "whisper_language": whisper_language,
        "whisper_translated": whisper_translated,
        "summary_analysis": result["summary"],
        "entities_legacy": "; ".join(entities),
        "topics_legacy": "; ".join(topics),
        "positive": "; ".join(value for value in sentiments if "positive" in value.casefold()),
        "neutral": "; ".join(value for value in sentiments if "neutral" in value.casefold()),
        "negative": "; ".join(value for value in sentiments if "negative" in value.casefold()),
        "us_legacy": "; ".join(result["us"]),
        "them_legacy": "; ".join(result["them"]),
        "formula_of_populism_analysis": _legacy_scalar(formula),
        "formula_of_populism_us": _legacy_scalar((formula or {}).get("us") if isinstance(formula, dict) else ""),
        "formula_of_populism_frontier": _legacy_scalar((formula or {}).get("frontier") if isinstance(formula, dict) else ""),
        "recording_datetime": result["source_timestamp"],
        "recording_date": str(result["source_timestamp"])[:10] if result["source_timestamp"] else "",
        "video_id": native_ids.get("video_id") or native_ids.get("videoId") or "",
        "allas_filename": object_ref,
        "new_id": native_ids.get("new_id") or native_ids.get("video_id") or native_ids.get("videoId") or "",
        "old_id": native_ids.get("old_id", ""),
        "new_entity": "; ".join(entities),
        "new_theme": "; ".join(topics),
        "raw_ref": result["raw_ref"],
        "raw_payload_json": (
            "" if raw_capture.get("payload") is None else json.dumps(raw_capture.get("payload"), ensure_ascii=False, sort_keys=True)
        ),
        "human_readable_summary": result["human_readable_summary"],
        "human_readable_markdown": result["human_readable_markdown"],
    }
    for index in range(1, 7):
        canonical_aliases[f"ocr_{index}"] = ocr[index - 1] if index <= len(ocr) else ""
        canonical_aliases[f"frame_{index}"] = frame_analysis[index - 1] if index <= len(frame_analysis) else ""
    for key, value in canonical_aliases.items():
        if value not in (None, "", [], {}):
            aliases[key] = value
        else:
            aliases.setdefault(key, value)
    for key in LEGACY_COLUMNS:
        aliases.setdefault(key, "")
        result[key] = aliases[key]
    return result
