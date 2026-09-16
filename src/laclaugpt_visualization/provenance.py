"""Researcher-facing provenance helpers.

Visualization consumes provenance emitted by Collection and Analysis.  This module is
intentionally read-only: it normalizes safe identifiers for display/filtering and never
reconstructs private configuration, prompts, codebooks or context payloads.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

UNKNOWN = "unknown / not recorded"

# Fields that are useful to researchers and safe to surface as identifiers.  Values are
# resolved from canonical records, analysis.model_runs and provenance events using aliases
# kept deliberately broad while producers converge on the shared contract.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "run_id": ("run_id", "analysis_run_id", "execution_id"),
    "study_id": ("study_id", "project_id", "project", "study"),
    "arena": ("arena", "arena_id"),
    "dataset": ("dataset", "dataset_id", "collection"),
    "country": ("country", "source_country"),
    "language": ("language", "source_language"),
    "effective_config_version": ("effective_config_version", "config_version"),
    "effective_config_hash": ("effective_config_hash", "config_hash", "configuration_hash"),
    "execution_profile": ("execution_profile", "machine_profile", "runtime_profile", "machine"),
    "context_profile": ("context_profile", "analysis_context_profile", "profile"),
    "codebook_id": ("codebook_id", "codebook_identifier", "codebook"),
    "codebook_version": ("codebook_version",),
    "codebook_hash": ("codebook_hash", "codebook_sha", "codebook_fingerprint"),
    "model": ("model", "model_id", "llm_model"),
    "backend": ("backend", "provider", "llm_backend"),
    "task_profile": ("task_profile", "model_profile", "llm_profile"),
    "embedding_model": ("embedding_model", "embedding_model_id"),
    "index_version": ("index_version", "embedding_index_version", "vector_index_version"),
    "previous_summary_id": ("previous_summary_id", "daily_summary_id", "prior_summary_id"),
    "pipeline_version": ("pipeline_version", "analysis_pipeline_version", "version"),
    "validation_status": ("validation_status", "human_validation_status", "review_status"),
    "collection_config_id": ("collection_config_id", "collection_provenance_id", "collection_run_id"),
}

BOOL_ALIASES: dict[str, tuple[str, ...]] = {
    "rag_enabled": ("rag_enabled", "retrieval_enabled", "use_rag"),
    "context_memory_enabled": ("context_memory_enabled", "memory_enabled", "use_context_memory"),
}

LIST_ALIASES: dict[str, tuple[str, ...]] = {
    "retrieval_ids": ("retrieval_ids", "retrieval_id", "query_ids", "query_id", "request_ids", "request_id"),
    "context_source_refs": (
        "context_source_refs",
        "context_record_ids",
        "context_records",
        "source_records",
        "memory_refs",
    ),
}

# Never expose values beneath these keys, even when a producer accidentally places them in
# provenance.  Safe views are allowlisted as well, so this is defence in depth.
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
    "run_id",
    "analysis_run_id",
    "execution_id",
    "study_id",
    "project_id",
    "arena",
    "dataset",
    "country",
    "language",
    "effective_config_version",
    "config_version",
    "effective_config_hash",
    "config_hash",
    "execution_profile",
    "machine_profile",
    "runtime_profile",
    "context_profile",
    "analysis_context_profile",
    "codebook_id",
    "codebook_identifier",
    "codebook_version",
    "codebook_hash",
    "codebook_fingerprint",
    "model",
    "model_id",
    "provider",
    "backend",
    "task_profile",
    "model_profile",
    "embedding_model",
    "embedding_model_id",
    "index_version",
    "embedding_index_version",
    "rag_enabled",
    "retrieval_enabled",
    "context_memory_enabled",
    "memory_enabled",
    "retrieval_id",
    "retrieval_ids",
    "query_id",
    "query_ids",
    "request_id",
    "request_ids",
    "context_source_refs",
    "context_record_ids",
    "source_records",
    "previous_summary_id",
    "daily_summary_id",
    "pipeline_version",
    "analysis_pipeline_version",
    "validation_status",
    "human_validation_status",
    "collection_config_id",
    "collection_provenance_id",
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
    """Return mappings from most specific/recent to broadest fallback."""
    raw = _mapping(row.get("raw_record"))
    analysis = _mapping(raw.get("analysis"))
    source = _mapping(raw.get("source"))
    model_runs = row.get("model_runs") or analysis.get("model_runs") or []
    model_mappings = [value for value in model_runs if isinstance(value, Mapping)] if isinstance(model_runs, list) else []
    provenance = _events(row)
    return [*reversed(provenance), *reversed(model_mappings), analysis, source, raw, row]


def _first(row: Mapping[str, Any], aliases: Iterable[str]) -> Any:
    for mapping in _candidate_mappings(row):
        for alias in aliases:
            value = mapping.get(alias)
            if _present(value):
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
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                identifier = next(
                    (
                        item.get(key)
                        for key in ("source_url", "source_id", "record_id", "id", "ref")
                        if _present(item.get(key))
                    ),
                    None,
                )
                if identifier is not None:
                    result.append(str(identifier))
            elif _present(item):
                result.append(str(item))
        return list(dict.fromkeys(result))
    return [str(value)]


def summarize_provenance(row: Mapping[str, Any]) -> dict[str, Any]:
    """Create a compact safe provenance summary for one normalized record."""
    summary: dict[str, Any] = {}
    for field, aliases in FIELD_ALIASES.items():
        value = _first(row, aliases)
        summary[field] = str(value) if _present(value) else UNKNOWN

    # Canonical flattened aliases are reliable fallbacks for source dimensions.
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

    # Presence of retrieval/context references is evidence that the facility was used even
    # when an older producer did not emit explicit booleans.
    if summary["rag_enabled"] is None and summary["retrieval_ids"]:
        summary["rag_enabled"] = True
    if summary["context_memory_enabled"] is None and summary["context_source_refs"]:
        summary["context_memory_enabled"] = True
    return summary


def safe_provenance_events(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return allowlisted provenance event fields, dropping accidental secret payloads."""
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
            if isinstance(value, (list, tuple, set)):
                clean[key] = _as_list(value)
            else:
                clean[key] = value
        if clean:
            safe.append(clean)
    return safe


def provenance_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Project normalized records into filterable provenance columns."""
    columns = [*FIELD_ALIASES, *BOOL_ALIASES, *LIST_ALIASES]
    if frame.empty:
        return pd.DataFrame(columns=columns, index=frame.index)
    rows = [summarize_provenance(row) for row in frame.to_dict(orient="records")]
    return pd.DataFrame(rows, index=frame.index, columns=columns)


def mixed_provenance_dimensions(frame: pd.DataFrame) -> dict[str, list[str]]:
    """Identify material provenance dimensions that differ within the current view."""
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
        if field not in projected:
            continue
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
