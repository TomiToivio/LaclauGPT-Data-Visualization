"""Safe researcher-facing provenance projections.

Visualization consumes Collection/Analysis provenance. It never executes codebooks,
reconstructs private configuration, or renders private prompt/context payloads.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

UNKNOWN = "unknown / not recorded"

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "run_id": ("run_id", "analysis_run_id", "execution_id"),
    "study_id": ("study_id", "project_id", "project", "study"),
    "arena": ("arena", "arena_id"),
    "dataset": ("dataset", "dataset_id", "collection"),
    "country": ("country", "source_country"),
    "language": ("language", "source_language"),
    "effective_config_version": ("effective_config_version", "config_version"),
    "effective_config_hash": (
        "effective_config_hash",
        "config_hash",
        "configuration_hash",
        "config_sha256",
    ),
    "execution_profile": (
        "execution_profile",
        "machine_profile",
        "runtime_profile",
        "machine",
    ),
    "context_profile": ("context_profile", "analysis_context_profile", "profile"),
    "codebook_id": ("codebook_id", "codebook_identifier"),
    "codebook_version": ("codebook_version",),
    "codebook_hash": (
        "codebook_hash",
        "codebook_sha",
        "codebook_sha256",
        "codebook_fingerprint",
    ),
    "model": ("model", "model_id", "llm_model"),
    "backend": ("backend", "provider", "llm_backend"),
    "task_profile": ("task_profile", "model_profile", "llm_profile"),
    "embedding_model": ("embedding_model", "embedding_model_id"),
    "index_version": (
        "index_version",
        "embedding_index_version",
        "vector_index_version",
    ),
    "previous_summary_id": (
        "previous_summary_id",
        "daily_summary_id",
        "prior_summary_id",
    ),
    "pipeline_version": ("pipeline_version", "analysis_pipeline_version"),
    "validation_status": (
        "validation_status",
        "human_validation_status",
        "review_status",
    ),
    "collection_config_id": (
        "collection_config_id",
        "collection_provenance_id",
        "collection_run_id",
    ),
}

BOOL_ALIASES = {
    "rag_enabled": ("rag_enabled", "retrieval_enabled", "use_rag"),
    "context_memory_enabled": (
        "context_memory_enabled",
        "memory_enabled",
        "use_context_memory",
    ),
}

LIST_ALIASES = {
    "retrieval_ids": (
        "retrieval_ids",
        "retrieval_id",
        "query_ids",
        "query_id",
        "request_ids",
        "request_id",
    ),
    "context_source_refs": (
        "context_source_refs",
        "context_record_ids",
        "context_records",
        "source_records",
        "memory_refs",
    ),
}

SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "connection_string",
    "mongodb_uri",
    "redis_url",
    "private_prompt",
    "prompt_text",
    "codebook_content",
    "researcher_note",
)

SAFE_EVENT_KEYS = {
    "stage",
    "method",
    "created_at",
    "producer",
    *{alias for aliases in FIELD_ALIASES.values() for alias in aliases},
    *{alias for aliases in BOOL_ALIASES.values() for alias in aliases},
    *{alias for aliases in LIST_ALIASES.values() for alias in aliases},
}


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _events(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = row.get("provenance", [])
    if not isinstance(value, list):
        return []
    return [event for event in value if isinstance(event, Mapping)]


def _candidate_mappings(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = _mapping(row.get("raw_record"))
    analysis = _mapping(raw.get("analysis"))
    source = _mapping(raw.get("source"))
    model_runs = row.get("model_runs") or analysis.get("model_runs") or []
    models = (
        [value for value in model_runs if isinstance(value, Mapping)]
        if isinstance(model_runs, list)
        else []
    )
    return [*reversed(_events(row)), *reversed(models), analysis, source, raw, row]


def _first(row: Mapping[str, Any], aliases: Iterable[str]) -> Any:
    for mapping in _candidate_mappings(row):
        for alias in aliases:
            value = mapping.get(alias)
            if _present(value) and not isinstance(value, Mapping):
                return value
    return None


def _nested(row: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    for mapping in _candidate_mappings(row):
        value = mapping.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _nested_value(mapping: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if _present(value) and not isinstance(value, Mapping):
            return value
    return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not pd.isna(value):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "1", "enabled", "on"}:
            return True
        if normalized in {"false", "no", "0", "disabled", "off"}:
            return False
    return None


def _as_list(value: Any) -> list[str]:
    if not _present(value):
        return []
    if not isinstance(value, (list, tuple, set)):
        return [str(value)]
    result: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            identifier = _nested_value(
                item,
                ("source_url", "source_id", "record_id", "id", "ref"),
            )
            if identifier is not None:
                result.append(str(identifier))
        elif _present(item):
            result.append(str(item))
    return list(dict.fromkeys(result))


def _apply_nested_runtime_fields(row: Mapping[str, Any], summary: dict[str, Any]) -> None:
    codebook = _nested(row, "codebook")
    if codebook:
        nested = {
            "codebook_id": _nested_value(codebook, ("codebook_id", "id", "name")),
            "codebook_version": _nested_value(codebook, ("version", "codebook_version")),
            "codebook_hash": _nested_value(
                codebook,
                ("sha256", "hash", "fingerprint", "codebook_hash"),
            ),
        }
        for field, value in nested.items():
            if summary[field] == UNKNOWN and _present(value):
                summary[field] = str(value)

    routing = _nested(row, "model_routing")
    if routing:
        nested = {
            "model": _nested_value(routing, ("model", "model_id", "name")),
            "backend": _nested_value(routing, ("backend", "provider")),
            "task_profile": _nested_value(routing, ("task_profile", "profile")),
        }
        for field, value in nested.items():
            if summary[field] == UNKNOWN and _present(value):
                summary[field] = str(value)


def summarize_provenance(row: Mapping[str, Any]) -> dict[str, Any]:
    """Create a compact safe provenance summary for one normalized record."""
    summary: dict[str, Any] = {}
    for field, aliases in FIELD_ALIASES.items():
        value = _first(row, aliases)
        summary[field] = str(value) if _present(value) else UNKNOWN

    _apply_nested_runtime_fields(row, summary)

    for field, fallback in (
        ("country", row.get("source_country")),
        ("language", row.get("source_language")),
        ("validation_status", row.get("review_status")),
    ):
        if summary[field] == UNKNOWN and _present(fallback):
            summary[field] = str(fallback)

    codebook_refs = _as_list(row.get("codebook_refs"))
    if summary["codebook_id"] == UNKNOWN and codebook_refs:
        summary["codebook_id"] = codebook_refs[0]

    for field, aliases in BOOL_ALIASES.items():
        summary[field] = _as_bool(_first(row, aliases))

    memory_refs = _as_list(row.get("memory_refs"))
    for field, aliases in LIST_ALIASES.items():
        values = _as_list(_first(row, aliases))
        if field == "context_source_refs":
            values = list(dict.fromkeys([*values, *memory_refs]))
        summary[field] = values

    if summary["rag_enabled"] is None and summary["retrieval_ids"]:
        summary["rag_enabled"] = True
    if summary["context_memory_enabled"] is None and summary["context_source_refs"]:
        summary["context_memory_enabled"] = True
    return summary


def safe_provenance_events(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return allowlisted scalar/list event fields and drop private payloads."""
    safe: list[dict[str, Any]] = []
    for event in _events(row):
        clean: dict[str, Any] = {}
        for key, value in event.items():
            normalized = str(key).casefold()
            if any(part in normalized for part in SENSITIVE_KEY_PARTS):
                continue
            if key not in SAFE_EVENT_KEYS or not _present(value):
                continue
            if isinstance(value, Mapping):
                continue
            clean[key] = _as_list(value) if isinstance(value, (list, tuple, set)) else value
        if clean:
            safe.append(clean)
    return safe


def provenance_frame(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [*FIELD_ALIASES, *BOOL_ALIASES, *LIST_ALIASES]
    if frame.empty:
        return pd.DataFrame(columns=columns, index=frame.index)
    rows = [summarize_provenance(row) for row in frame.to_dict(orient="records")]
    return pd.DataFrame(rows, index=frame.index, columns=columns)


def mixed_provenance_dimensions(frame: pd.DataFrame) -> dict[str, list[str]]:
    projected = provenance_frame(frame)
    material = (
        "run_id",
        "effective_config_hash",
        "context_profile",
        "codebook_id",
        "codebook_version",
        "codebook_hash",
        "model",
        "backend",
        "task_profile",
        "pipeline_version",
    )
    mixed: dict[str, list[str]] = {}
    for field in material:
        values = sorted(
            {
                str(value)
                for value in projected[field]
                if _present(value) and str(value) != UNKNOWN
            }
        )
        if len(values) > 1:
            mixed[field] = values
    return mixed


def comparison_warning(frame: pd.DataFrame) -> str | None:
    mixed = mixed_provenance_dimensions(frame)
    if not mixed:
        return None
    labels = ", ".join(field.replace("_", " ") for field in mixed)
    return (
        "The current comparison mixes materially different provenance: "
        f"{labels}. Interpret differences cautiously and inspect the run/config fingerprints."
    )
