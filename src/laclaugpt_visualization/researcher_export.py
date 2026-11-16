"""Researcher-facing projection of the live-steps index (issue #242).

The index carries 126 columns because it keeps every stage's status, model name, runtime and
orchestrator bookkeeping alongside the findings. A researcher needs the findings. This module is the
allowlist that separates them: it names the columns a researcher may see and export, records the
reason every other column was dropped, and **refuses to guess** — an unknown column is an error, not
a silent pass-through, because a pipeline change that adds a field must not leak it into an export.

The artifact builder already classifies source columns when it writes ``MANIFEST.json``; this is the
second gate, applied at export time to the frame the app actually holds. Two gates is deliberate: the
builder protects the corpus, this protects the download.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

#: Columns a researcher may read and export. Identity, source metadata, human-readable stage
#: statuses, the step 6–8 findings and the researcher's own annotations. Runtime, prompt and
#: persistence plumbing is excluded by :data:`DROPPED`.
RESEARCH_COLUMNS: tuple[str, ...] = (
    "record_id",
    "country",
    "video_id",
    "source_type",
    "source_recording",
    "sequence_number",
    "author_username",
    "account_type",
    "political_preference",
    "video_duration",
    "video_duration_seconds",
    "record_date",
    "month",
    "duration_minutes",
    "video_status",
    "video_quality_status",
    "video_quality_reason",
    "processing_status",
    "processing_status_reason",
    "preprocess_status",
    "preprocess_note",
    "preprocess_completed_at",
    "asr_backend",
    "asr_language",
    "asr_model",
    "ocr_backend",
    "ocr_model",
    "frame_analysis_status",
    "frame_analysis_model",
    "frame_timestamp_seconds",
    "frame_analysis_timestamp_seconds",
    "frame_quality_status",
    "frame_quality_reason",
    "vllm_video_status",
    "vllm_video_model",
    "summary_quality_status",
    "summary_quality_reason",
    "laclau_status",
    "laclau_formula_conditions_met",
    "laclau_generated_at",
    "laclau_abstention_reason",
    "formula_of_populism_analysis",
    "formula_of_populism_us",
    "formula_of_populism_frontier",
    "dna_status",
    "dna_statement_count",
    "dna_binary_count",
    "dna_uncertain_count",
    "dna_actor_unresolved_count",
    "dna_concept_novel_count",
    "dna_generated_at",
    "dna_error",
    "sna_status",
    "sna_schema_version",
    "sna_generated_at",
    "sna_error",
    "positive",
    "neutral",
    "negative",
    "postprocess_entities",
    "postprocess_themes",
    "entities",
    "themes",
    "researcher_note",
    "needs_resplit",
    "needs_human_review",
    "step_01_status",
    "step_02_status",
    "step_03_status",
    "step_04_status",
    "step_05_status",
    "step_06_status",
    "step_07_status",
    "pipeline_steps_ok",
    "has_sna",
)

#: Everything else, grouped by *why* it is not researcher material. The reason travels into the
#: export's provenance block, so a dropped column is explained rather than merely absent.
DROPPED: dict[str, tuple[str, ...]] = {
    "storage path or backend identifier": (
        "_storage_id",
        "allas_filename",
        "frame_file",
        "video_filename",
        "vllm_video_allas_source",
    ),
    "runtime and hardware telemetry": (
        "asr_runtime_ms",
        "ocr_runtime_ms",
        "vllm_video_runtime_seconds",
        "vllm_video_inference_seconds",
        "vllm_video_analysis_duration_seconds",
        "vllm_video_analyzed_duration_seconds",
        "vllm_video_source_duration_seconds",
        "vllm_video_bytes",
        "vllm_gpu_name",
        "vllm_peak_gpu_memory_mb",
        "vllm_cuda_version",
        "vllm_torch_version",
        "vllm_hostname",
        "laclau_runtime_seconds",
        "dna_runtime_seconds",
    ),
    "orchestrator or reprocessing bookkeeping": (
        "_monday500_reused_through",
        "include_in_reprocess",
        "cleaning_rule_id",
        "cleaning_status",
        "context_evidence_role",
        "vllm_video_source_row_index",
        "vllm_video_selected_index",
        "vllm_video_source_id",
        "step4_summary_provenance",
        "entities_seed_provenance",
        "themes_seed_provenance",
    ),
    "persistence or debug status": (
        "laclau_persistence_status",
        "dna_persistence_status",
        "vllm_video_persistence_status",
        "vllm_video_structured_output_status",
        "vllm_structured_status",
        "vllm_video_trim_exit_status",
        "laclau_context_truncated",
        "dna_context_truncated",
        "sna_context_truncated",
    ),
    "prompt and model plumbing": (
        "laclau_prompt_version",
        "dna_prompt_version",
        "sna_prompt_version",
        "sna_castells_prompt_version",
        "vllm_video_prompt_version",
        "vllm_version",
        "vllm_video_version",
        "vllm_video_api",
    ),
    "legacy dashboard scroll bookkeeping": (
        "SCROLL",
        "SCROLL_SECONDS",
        "video_initial_skip_seconds",
    ),
}


#: The reason an unknown column carries when it is excluded without being classified.
UNCLASSIFIED_REASON = (
    "not classified for researcher export — excluded by default; classify it in "
    "laclaugpt_visualization/researcher_export.py"
)


class UnclassifiedColumnError(ValueError):
    """A column is in neither the allowlist nor the drop list, and strict classification was asked for.

    The default is to *exclude* an unknown column: a producer field that appears between builds must
    not reach a researcher's CSV, and it must not take the dashboard down either. The verification
    script runs ``classify(..., strict=True)`` over the served corpus, so the drift is reported as a
    failed check instead of as an absent column nobody notices.
    """


def _drop_reasons() -> dict[str, str]:
    return {column: reason for reason, columns in DROPPED.items() for column in columns}


def classify(
    columns: Iterable[str], *, strict: bool = False
) -> tuple[list[str], list[dict[str, str]]]:
    """Split ``columns`` into the exporter's allowlist and the drops, with reasons.

    Order follows the input, so the export's column order is the app's column order and not an
    artefact of this module. An unclassified column is excluded with :data:`UNCLASSIFIED_REASON`;
    with ``strict=True`` it raises instead, which is how the deployment check reports producer drift.
    """
    reasons = _drop_reasons()
    keep: list[str] = []
    dropped: list[dict[str, str]] = []
    unknown: list[str] = []
    for column in columns:
        if column in RESEARCH_COLUMNS:
            keep.append(column)
        elif column in reasons:
            dropped.append({"column": column, "reason": reasons[column]})
        else:
            unknown.append(column)
            dropped.append({"column": column, "reason": UNCLASSIFIED_REASON})
    if unknown and strict:
        raise UnclassifiedColumnError(
            "columns are neither researcher fields nor known machine fields: "
            + ", ".join(sorted(unknown))
            + ". Classify them in laclaugpt_visualization/researcher_export.py."
        )
    return keep, dropped


def researcher_frame(frame: pd.DataFrame, columns: Sequence[str] | None = None) -> pd.DataFrame:
    """The researcher projection of ``frame``: allowlisted columns only, same row order.

    ``columns`` narrows the projection further (a column chooser in the UI); it can never add a
    column that is not on the allowlist.
    """
    keep, _ = classify(frame.columns)
    # ``None`` means "the whole allowlist"; an explicit empty list means "no columns". Using
    # ``columns or keep`` conflated the two, so a researcher who deselected everything got the
    # entire projection back.
    requested = keep if columns is None else columns
    chosen = [column for column in requested if column in keep]
    if not chosen:
        return frame.iloc[0:0].copy()
    return frame.loc[:, chosen].copy()


def csv_bytes(frame: pd.DataFrame) -> bytes:
    """UTF-8 CSV with a BOM, because researchers open exports in Excel.

    Deterministic for a given frame: same rows, same bytes.
    """
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def selection_summary(frame: pd.DataFrame) -> dict[str, Any]:
    """What the researcher is looking at, in the terms the filters use."""
    countries: dict[str, int] = {}
    if "country" in frame.columns:
        countries = {
            str(country): int(count) for country, count in frame["country"].value_counts().sort_index().items()
        }
    return {"rows": len(frame), "countries": countries}


def served_commit(root: str | Path | None) -> str | None:
    """The commit of the checkout that is actually being served, or ``None``.

    Read from the running code's own directory rather than from a constant, so the UI can state what
    it is serving instead of what it was built from. A detached worktree is the documented Laskin
    convention, so a detached HEAD is a normal answer here, not an error.
    """
    if root is None:
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def manifest_fingerprint(manifest: Mapping[str, Any]) -> str | None:
    """A stable digest of the manifest, so an export can name the build it came from."""
    if not manifest:
        return None
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def provenance(
    manifest: Mapping[str, Any],
    *,
    frame: pd.DataFrame,
    selection: pd.DataFrame,
    commit: str | None,
    exported_at: datetime | None = None,
) -> dict[str, Any]:
    """The record that makes an export defensible: what was exported, from which build, by what code."""
    keep, dropped = classify(frame.columns)
    exported_at = exported_at or datetime.now(UTC)
    return {
        "contract": "ep24-researcher-export/1",
        "exported_at": exported_at.isoformat(),
        "served_commit": commit,
        "dataset": manifest.get("dataset") or manifest.get("contract"),
        "manifest_generated_at": manifest.get("generated_at"),
        "manifest_contract": manifest.get("contract"),
        "manifest_builder_version": manifest.get("builder_version"),
        "manifest_sha256": manifest_fingerprint(manifest),
        "corpus_records": manifest.get("records"),
        "corpus_record_counts": manifest.get("record_counts"),
        "selection": selection_summary(selection),
        "columns": list(keep),
        "dropped_columns": dropped,
        "note": (
            "Read-only projection of the EP24 live pipeline artifacts. Counts describe the corpus the "
            "export came from; the selection describes the filtered rows in this file."
        ),
    }


def provenance_json(payload: Mapping[str, Any]) -> bytes:
    """Indented, sorted JSON so two exports of one selection diff cleanly."""
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
