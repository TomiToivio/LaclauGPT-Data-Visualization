"""Read-only Phase 0 -> Visualization compatibility adapter.

Phase 0 records are not canonical Phase 1 records. This module exposes only the
small descriptive view required by the existing visualization transforms while
preserving the original Phase 0 structures under an explicit compatibility
boundary.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

_PHASE0_KEYS = (
    "phase0",
    "phase0_summary_raw",
    "phase0_summary",
    "phase0_summary_error_metadata",
    "phase0_summary_validated",
    "phase0_summary_validation_error",
    "phase0_discourse_raw",
    "phase0_discourse",
    "phase0_discourse_error_metadata",
    "phase0_ontology",
)

_STAGE_ORDER = ("preprocess", "summary", "postprocess", "discourse")


def looks_like_phase0(record: dict[str, Any]) -> bool:
    """Return True when a record carries the Phase 0 analysis contract."""
    return any(key in record for key in _PHASE0_KEYS)


def _list(value: Any) -> list[Any]:
    return deepcopy(value) if isinstance(value, list) else []


def _text_value(*values: Any) -> str:
    """Return the first non-empty scalar while treating DataFrame NaN as missing."""
    for value in values:
        if value is None:
            continue
        if isinstance(value, float) and math.isnan(value):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _labels(value: Any) -> list[str]:
    """Extract already-present labels without interpreting their meaning."""
    result: list[str] = []
    for item in _list(value):
        if isinstance(item, dict):
            label = (
                item.get("label")
                or item.get("name")
                or item.get("text")
                or item.get("canonical_label")
            )
        else:
            label = item
        if label is not None and str(label).strip():
            result.append(str(label).strip())
    return result


def _stage_snapshot(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = record.get("phase0")
    phase0 = raw if isinstance(raw, dict) else {}
    stages: dict[str, dict[str, Any]] = {}
    for stage in _STAGE_ORDER:
        value = phase0.get(stage)
        stages[stage] = deepcopy(value) if isinstance(value, dict) else {"status": "pending"}
    return stages


def _overall_status(stages: dict[str, dict[str, Any]]) -> str:
    statuses = [
        str(stages[name].get("status") or "pending").casefold() for name in _STAGE_ORDER
    ]
    if "error" in statuses:
        return "error"
    if statuses[-1] == "ok":
        return "analyzed"
    return "awaiting-analysis"


def _latest_stage_update(stages: dict[str, dict[str, Any]]) -> str:
    """Return the latest already-recorded Phase 0 stage update timestamp."""
    values = [
        str(stages[name].get("updated_at") or "").strip()
        for name in _STAGE_ORDER
        if str(stages[name].get("updated_at") or "").strip()
    ]
    return max(values, default="")


def adapt_phase0(record: dict[str, Any]) -> dict[str, Any]:
    """Project one Phase 0 Mongo document into a deterministic read-only view.

    The returned mapping deliberately omits canonical provenance and review fields.
    Compatibility/source-stage metadata stays namespaced under phase0_compatibility
    so callers cannot mistake it for canonical Phase 1 provenance.
    """
    source = deepcopy(record)
    metadata_raw = source.get("metadata")
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    validated_raw = source.get("phase0_summary_validated")
    validated = validated_raw if isinstance(validated_raw, dict) else {}
    summary_raw = source.get("phase0_summary")
    summary = summary_raw if isinstance(summary_raw, dict) else {}
    discourse_raw = source.get("phase0_discourse")
    discourse = discourse_raw if isinstance(discourse_raw, dict) else {}
    stages = _stage_snapshot(source)

    source_url = _text_value(
        source.get("source_url"),
        validated.get("source_url"),
        metadata.get("source_url"),
    )
    source_date = _text_value(
        source.get("source_date"),
        validated.get("source_date"),
        metadata.get("source_date"),
    )
    actor = _text_value(
        source.get("actor_name"),
        validated.get("actor_name"),
        metadata.get("actor_name"),
        source.get("source_name"),
    )
    language = _text_value(source.get("language"), metadata.get("language"))
    title = _text_value(source.get("title"), validated.get("title"), metadata.get("title"))
    arena = _text_value(source.get("arena"), metadata.get("arena"))

    entities = _labels(validated.get("entities") or summary.get("entities"))
    topics = _labels(validated.get("topics") or summary.get("topics"))
    signifiers = _labels(validated.get("signifiers") or summary.get("signifiers"))
    discourse_signifiers = _labels(discourse.get("signifiers"))
    for label in discourse_signifiers:
        if label not in signifiers:
            signifiers.append(label)

    formations: list[str] = []
    for field in ("ai_formation", "political_formation"):
        value = _text_value(source.get(field), metadata.get(field))
        if value:
            formations.append(value)

    summary_text = str(validated.get("summary") or summary.get("summary") or "")
    document_id = str(source.get("document_id") or source_url)
    raw_phase0 = {
        key: deepcopy(source[key]) for key in _PHASE0_KEYS if key in source
    }

    return {
        "document_id": document_id,
        "source_url": source_url,
        "source_timestamp": source_date,
        "analysis_timestamp": _latest_stage_update(stages),
        "source_author": str(actor),
        "source_language": str(language),
        "source_arena": str(arena),
        "content_title": str(title),
        "summary": summary_text,
        "human_readable_summary": summary_text,
        "entities": entities,
        "topics": topics,
        "signifiers": signifiers,
        "formations": formations,
        "analysis_status": _overall_status(stages),
        "phase0_stage_status": stages,
        "phase0_compatibility": {
            "contract": "phase0-analysis-compatibility-v1",
            "canonical_phase1_record": False,
            "source_identity": "source_url",
            "label_semantics": {
                "summary_signifiers": "descriptive",
                "discourse_signifiers": "candidate",
                "formations": "provisional-context",
            },
            "raw_phase0": raw_phase0,
        },
    }
