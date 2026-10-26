#!/usr/bin/env python3
"""Streaming EP24 exporter — the large-frame variant of the #195 export.

`export_visualization_data.py` is the canonical, documented CLI (`--countries/--input`, `qa.json`,
`records.jsonl`, `record_id`). It loads each frame with pandas, which is right for the smaller
per-country exports and for the synthetic fixtures.

This module exists for the frames that are actually large — the Finnish cumulative frame is 1.1 GB
with cells holding whole JSON analyses — and for sources that are *not* the reprocessed schema at
all: it streams the CSV, so memory stays proportional to one row, and it can export a
pre-Roihu ("legacy") frame without pretending the reprocessed stages ran.

It writes a different, richer artifact set (a gzipped text bundle per stage, normalized child
tables, `MANIFEST.json` per-stage coverage with denominators, `QA_REPORT.md`). Use it when
`export_visualization_data.py` cannot: a >500 MB frame, a legacy-only country, or a shared file out
of which one country must be selected.

Design rules (all of them are tested):

* **one row per video**, keyed by ``country`` + ``video_id`` (``_storage_id`` when present);
  duplicates are counted, not silently dropped; rows without a usable id are reported and
  excluded from the canonical view;
* **every source column is classified** — kept, derived, or dropped *with a reason* — and the
  unaccounted list must be empty, so a producer contract change fails the build loudly;
* **machine-readable and human-readable** forms of every stage are kept side by side; no
  double-encoded JSON strings in user-facing fields;
* **normalized children** for one-to-many data (entities, discourse claims, DNA statements,
  SNA nodes/edges), each row carrying its parent ``record_key`` and any evidence quote;
* **provenance and honesty**: stage coverage is measured, never assumed; a missing stage is
  reported as missing, and a status field is never read as interpretation validity;
* **privacy**: this script only reads local files, opens them read-only, writes no
  credentials, and refuses to write outside ``--output``.

Usage::

    python scripts/ep24/export_visualization_data.py \\
        --source finland=/data/ep24_finland_reprocessed_complete.csv \\
        --source poland=/data/ep24_poland_dashboard.csv \\
        --output /private/ep24/export

    # a quick development subset
    python scripts/ep24/export_visualization_data.py --source finland=big.csv --limit 50 ...
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

csv.field_size_limit(200 * 1024 * 1024)

BUILDER_VERSION = "ep24-export-1"

#: Country keys the dashboard knows. Anything else is refused rather than guessed.
COUNTRIES: tuple[str, ...] = ("finland", "poland", "portugal")

#: Identity/provenance columns. Without these a row cannot be joined back to its source.
IDENTITY_COLUMNS: tuple[str, ...] = (
    "country", "video_id", "_storage_id", "allas_filename", "video_filename",
    "source_type", "source_recording", "sequence_number", "author_username",
    "account_type", "political_preference", "video_duration_seconds",
    "SCROLL", "SCROLL_SECONDS", "metadata", "video_duration", "vllm_video_source_id",
)

#: Per stage: the status column (does the stage exist for this record?), plus the fields a
#: researcher reads and the machine-readable output. Absent columns are simply not produced —
#: the manifest then reports that stage as unavailable for that country.
STAGE_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    "0_ingest": {
        "status": ("processing_status",),
        "human": ("processing_status_reason", "needs_resplit"),
        "machine": (),
    },
    "1_preprocess": {
        "status": ("preprocess_status",),
        "human": ("preprocess_note", "preprocess_completed_at", "asr_transcript",
                  "asr_translated", "ocr_1", "frame_file"),
        "machine": ("asr_language", "asr_backend", "asr_model", "ocr_backend", "ocr_model",
                    "frame_timestamp_seconds"),
    },
    "2_frame": {
        "status": ("frame_analysis_status",),
        "human": ("frame_analysis_1",),
        "machine": ("frame_analysis_model", "frame_analysis_timestamp_seconds",
                    "frame_quality_status", "frame_quality_reason"),
    },
    "3_video": {
        "status": ("vllm_video_status", "video_status"),
        "human": ("vllm_video_analysis", "vllm_video_markdown_analysis",),
        "machine": ("vllm_video_model", "vllm_video_structured_status",
                    "vllm_video_structured_json", "vllm_video_structured_output_status",
                    "vllm_structured_status", "vllm_structured_output",
                    "vllm_video_persistence_status", "video_quality_status",
                    "video_quality_reason"),
    },
    "4_summary": {
        "status": ("summary_quality_status",),
        "human": ("summary_analysis", "summary_summary_md"),
        "machine": ("summary_quality_reason", "step4_summary_provenance"),
    },
    "5_postprocess": {
        "status": ("postprocess_entities", "postprocess_themes"),
        "human": ("postprocess_summary_md", "ep24_entity_canonical_names",
                  "ep24_theme_canonical_names"),
        "machine": ("entities", "themes", "ep24_entity_ids", "ep24_entity_resolution_json",
                    "ep24_entity_unresolved_json", "ep24_theme_resolution_json",
                    "ep24_sentiment_targets_json", "entity_normalization_json",
                    "theme_normalization_json", "positive", "neutral", "negative"),
    },
    "6_discourse": {
        "status": ("laclau_status",),
        "human": ("laclau_summary_md", "formula_of_populism_analysis",
                  "formula_of_populism_frontier", "formula_of_populism_us",
                  "laclau_abstention_reason"),
        "machine": ("laclau_structured_json", "laclau_formula_conditions_met", "laclau_error",
                    "laclau_persistence_status", "context_evidence_role"),
    },
    "7_dna": {
        "status": ("dna_status",),
        "human": ("dna_analysis_markdown",),
        "machine": ("dna_statements_json", "dna_statement_count", "dna_binary_count",
                    "dna_uncertain_count", "dna_actor_unresolved_count",
                    "dna_concept_novel_count", "dna_error", "dna_persistence_status"),
    },
    "8_sna": {
        "status": ("sna_status",),
        "human": ("sna_report_markdown", "sna_castells_interpretation_markdown",
                  "sna_analysis_markdown"),
        "machine": ("sna_nodes_json", "sna_edges_json", "sna_metrics_json", "sna_error",
                    "sna_schema_version"),
    },
    "9_rdf": {
        "status": ("rdf_status",),
        "human": (),
        "machine": ("rdf_export_path", "rdf_triple_count", "rdf_resource_count", "rdf_error"),
    },
}

#: Columns deliberately excluded from the researcher-facing view, with the reason. Backend and
#: intermediate payloads are dropped; nothing that carries a finding, a status or provenance is.
DROP_REASONS: dict[str, str] = {
    "_pipeline": "orchestrator bookkeeping, not a finding",
    "_pipeline_step_6": "orchestrator bookkeeping, not a finding",
    "_pipeline_step_7": "orchestrator bookkeeping, not a finding",
    "_provenance": "duplicated by the export's own provenance block",
    "codebook_context_json": "prompt context payload (regenerable)",
    "memory_context_json": "prompt context payload (regenerable)",
    "rag_context_json": "retrieval payload (regenerable)",
    "ep24_codebook_context_json": "prompt context payload (regenerable)",
    "ep24_codebook_fingerprint": "backend cache key",
    "ep24_human_seed_context": "prompt context payload (regenerable)",
    "ep24_memory_entity_ids": "backend retrieval bookkeeping",
    "ep24_memory_theme_ids": "backend retrieval bookkeeping",
    "ep24_memory_topic_ids": "backend retrieval bookkeeping",
    "ep24_memory_sentiment_target_ids_json": "backend retrieval bookkeeping",
    "ep24_memory_unresolved_json": "backend retrieval bookkeeping",
    "ep24_seed_entities_json": "prompt seed payload (regenerable)",
    "ep24_seed_themes_json": "prompt seed payload (regenerable)",
    "laclau_codebook_context_json": "prompt context payload (regenerable)",
    "laclau_codebook_fingerprint": "backend cache key",
    "laclau_context_sha256": "context hash, not a finding",
    "laclau_context_truncated": "context bookkeeping",
    "laclau_generated_at": "timestamp of a model run; the export records its own",
    "laclau_memory_context_json": "prompt context payload (regenerable)",
    "laclau_model_metadata_json": "backend metadata dump",
    "laclau_prompt_version": "prompt bookkeeping",
    "laclau_rag_context_json": "retrieval payload (regenerable)",
    "laclau_raw_response": "raw model response, superseded by the structured output",
    "laclau_runtime_seconds": "backend performance telemetry",
    "dna_codebook_fingerprint": "backend cache key",
    "dna_context_sha256": "context hash, not a finding",
    "dna_context_truncated": "context bookkeeping",
    "dna_generated_at": "timestamp of a model run",
    "dna_memory_context_json": "prompt context payload (regenerable)",
    "dna_model_metadata_json": "backend metadata dump",
    "dna_prompt_version": "prompt bookkeeping",
    "dna_rag_context_json": "retrieval payload (regenerable)",
    "dna_raw_response": "raw model response, superseded by dna_statements_json",
    "dna_runtime_seconds": "backend performance telemetry",
    "sna_castells_prompt_version": "prompt bookkeeping",
    "sna_context_sha256": "context hash, not a finding",
    "sna_context_truncated": "context bookkeeping",
    "sna_generated_at": "timestamp of a model run",
    "sna_prompt_version": "prompt bookkeeping",
    "frame_analysis_context_sha256": "context hash, not a finding",
    "researcher_note": "kept as its own labelled column instead",
    "vllm_cuda_version": "runtime telemetry",
    "vllm_gpu_name": "runtime telemetry",
    "vllm_hostname": "runtime telemetry",
    "vllm_peak_gpu_memory_mb": "runtime telemetry",
    "vllm_torch_version": "runtime telemetry",
    "vllm_version": "runtime telemetry",
    "vllm_video_allas_source": "media path, duplicated by allas_filename",
    "vllm_video_api": "runtime telemetry",
    "vllm_video_bytes": "file size telemetry",
    "vllm_video_context_sha256": "context hash, not a finding",
    "vllm_video_error": "kept only when the stage failed; see vllm_video_status",
    "vllm_video_inference_seconds": "runtime telemetry",
    "vllm_video_local_path": "host path, not portable",
    "vllm_video_analysis_path": "host path, not portable",
    "vllm_video_remote_path": "host path, not portable",
    "vllm_video_remote_path_logged": "host path, not portable",
    "vllm_video_prompt": "prompt payload (regenerable)",
    "vllm_video_prompt_hash": "prompt bookkeeping",
    "vllm_video_prompt_sha256": "prompt bookkeeping",
    "vllm_video_prompt_version": "prompt bookkeeping",
    "vllm_video_raw_output": "raw model response, superseded by the structured output",
    "vllm_video_runtime_seconds": "runtime telemetry",
    "vllm_video_selected_index": "backend selection bookkeeping",
    "vllm_video_sha256": "media hash, not a finding",
    "vllm_video_source_row_index": "backend bookkeeping",
    "vllm_video_structured_output_error": "kept only when the stage failed",
    "vllm_video_trim_command": "backend command line",
    "vllm_video_trim_exit_status": "backend telemetry",
    "vllm_video_analysis_duration_seconds": "runtime telemetry",
    "vllm_video_analyzed_duration_seconds": "runtime telemetry",
    "vllm_video_version": "runtime telemetry",
    "asr_runtime_ms": "runtime telemetry",
    "ocr_runtime_ms": "runtime telemetry",
    "video_initial_skip_seconds": "ingest bookkeeping, duplicated by SCROLL_SECONDS",
    "vllm_video_source_duration_seconds": "duplicated by video_duration_seconds",
}

#: Per-stage status columns kept in the index, so the dashboard can filter on stage completion
#: without opening the text bundle.
INDEX_STATUS_COLUMNS: tuple[str, ...] = tuple(sorted({
    name for spec in STAGE_FIELDS.values() for name in spec["status"]
}))

#: Derived columns, computed by this exporter so the dashboard can filter without parsing JSON.
DERIVED_COLUMNS: dict[str, str] = {
    "record_key": "country/video_id, the stable join key of every artifact",
    "has_usable_id": "1 when a non-empty video_id exists; unusable rows are excluded from the view",
    "entity_count": "len(postprocess_entities)",
    "theme_count": "len(postprocess_themes)",
    "discourse_claim_count": "number of statements in laclau_structured_json",
    "dna_statement_total": "len(dna_statements_json)",
    "sna_node_count": "len(sna_nodes_json)",
    "sna_edge_count": "len(sna_edges_json)",
    "stage_status_summary": "comma-separated step=status pairs, for at-a-glance completeness",
    "researcher_note": "researcher coding, labelled separately from model output",
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def parse_json_cell(value: Any) -> Any:
    """Decode one CSV cell that may hold JSON. Returns None for empty/unparseable cells."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "[]", "{}"}:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def as_list(value: Any) -> list[Any]:
    """A cell that should be a list.

    JSON lists pass through. The pre-Roihu exports store entities/themes as a plain delimited string
    (``"poland, putin, ukraine"``), so a short, brace-free cell is split on its delimiters instead of
    being reported as an unparseable JSON blob.
    """
    parsed = parse_json_cell(value)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("items", "statements", "nodes", "edges", "entities", "themes", "claims"):
            if isinstance(parsed.get(key), list):
                return parsed[key]
        return [parsed]
    text_value = str(value or "").strip()
    if text_value and not any(ch in text_value for ch in "{[]}") and len(text_value) <= 400 \
            and "\n" not in text_value:
        for delimiter in (";", "|", ","):
            if delimiter in text_value:
                parts = [part.strip() for part in text_value.split(delimiter) if part.strip()]
                if 1 < len(parts) <= 50:
                    return parts
        if text_value.lower() not in EMPTY_CELLS and len(text_value.split()) <= 12:
            return [text_value]
    return []


#: Values that mean "no data" in a pandas/CSV export. They are empty, not unparseable.
EMPTY_CELLS: frozenset[str] = frozenset({"nan", "none", "null", "na", "n/a", "-", "[]", "{}", ""})


def is_empty(value: str) -> bool:
    return value.strip().lower() in EMPTY_CELLS


def cell(row: Mapping[str, str], name: str) -> str:
    return (row.get(name) or "").strip()


def first_cell(row: Mapping[str, str], names: Sequence[str]) -> str:
    for name in names:
        value = cell(row, name)
        if value:
            return value
    return ""


def clean_scalar(value: Any, limit: int = 400) -> str:
    """A single CSV-safe scalar: newlines collapsed, length bounded, no JSON blobs."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def identity_key(country: str, row: Mapping[str, str], *, require_video_id: bool = False) -> str:
    """A stable, collision-free key for one source row.

    ``video_id`` alone is **not** unique in the EP24 corpus (HEPP24 ids collide across folders and
    parts — up to nine rows share one id), so using it as the record key would silently merge
    distinct videos. The key therefore always carries a digest of the canonical identity tuple:
    media key, recording, segment and platform. The human-readable ``video_id`` stays a visible
    column, and only *identical* tuples are treated as duplicates.
    """
    if require_video_id and not (cell(row, "video_id") or cell(row, "_storage_id")):
        return ""
    media = cell(row, "allas_filename") or cell(row, "_storage_id")
    if media:
        # the contract calls allas_filename the authoritative media key; _storage_id is its fallback
        parts: tuple[str, ...] = (media, cell(row, "video_id"))
    else:
        parts = (cell(row, "video_id"), cell(row, "source_type"),
                 cell(row, "source_recording"), cell(row, "sequence_number"))
    if not any(parts):
        return ""
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:10]
    label = (cell(row, "video_id") or cell(row, "_storage_id")
             or Path(cell(row, "allas_filename")).stem or "record")
    return f"{country}/{label}#{digest}"


@dataclass
class CountryStats:
    country: str
    source_path: str
    source_bytes: int = 0
    source_sha256: str = ""
    source_columns: int = 0
    rows_read: int = 0
    rows_exported: int = 0
    duplicates: int = 0
    invalid_ids: int = 0
    stage_records: dict[str, int] = field(default_factory=dict)
    stage_unavailable: list[str] = field(default_factory=list)
    parse_failures: dict[str, int] = field(default_factory=dict)
    children: dict[str, int] = field(default_factory=dict)
    unaccounted_columns: list[str] = field(default_factory=list)



#: Legacy EP2024 schema (the 75-column dashboard export, pre-Roihu). Used with
#: ``--profile legacy`` for countries whose reprocessed cumulative frame is not available: the
#: export then reports every reprocessed stage as unavailable instead of pretending they ran.
LEGACY_KEEP: tuple[str, ...] = (
    "country", "video_id", "author_username", "account_type", "source_type", "source_recording",
    "video_filename", "allas_filename", "sequence_number", "recording_date", "recording_datetime",
    "day_number", "political_preference", "video_duration", "profile_name",
    "daily_file_number", "new_id", "new_filename", "old_id", "puhti_filename",
    "whisper_transcript", "whisper_language", "whisper_translated",
    "ocr_1", "ocr_2", "ocr_3", "ocr_4", "ocr_5", "ocr_6",
    "frame_1", "frame_2", "frame_3", "frame_4", "frame_5", "frame_6", "frames",
    "summary_analysis", "entities", "topics", "political_themes",
    "positive", "neutral", "negative",
    "formula_of_populism_analysis", "formula_of_populism_us",
    "formula_of_populism_frontier", "formula_of_populism_us_elements",
    "formula_of_populism_frontier_elements", "formula_of_populism_us_affects",
    "formula_of_populism_frontier_affects",
    "lda_topic", "lda_minor_topics", "lda_topic_words", "lda_minor_topic",
    "lda_15_topic", "lda_15_minor_topic", "lda_15_topic_words",
    "lda_40_topic", "lda_40_minor_topic", "lda_40_topic_words",
    "lda_country_topic", "lda_country_minor_topic", "lda_country_topic_words",
    "manifestoberta_predicted_class", "manifestoberta_probabilities",
    "new_entity", "new_theme", "spacy_entities", "us", "them",
)

LEGACY_DROP: dict[str, str] = {
    "video_file": "host-local media path, not portable",
    "split_number": "duplicate of sequence_number",
    "corrected_date": "cleaning bookkeeping; keeps original_date and corresponding_date",
    "original_date": "cleaning bookkeeping",
    "corresponding_date": "cleaning bookkeeping",
}


def classify_legacy(columns: Sequence[str]) -> tuple[list[str], dict[str, str], list[str]]:
    kept = [c for c in columns if c in LEGACY_KEEP]
    dropped = {c: LEGACY_DROP[c] for c in columns if c in LEGACY_DROP}
    unknown = [c for c in columns if c not in LEGACY_KEEP and c not in LEGACY_DROP]
    return kept, dropped, unknown


# --------------------------------------------------------------------------- #
# Column classification
# --------------------------------------------------------------------------- #


def classify_columns(columns: Sequence[str]) -> tuple[list[str], dict[str, str]]:
    """Split source columns into kept and dropped(with reason); anything else is unaccounted."""
    stage_cols: set[str] = set()
    for stage in STAGE_FIELDS.values():
        for group in stage.values():
            stage_cols.update(group)

    kept: list[str] = []
    dropped: dict[str, str] = {}
    for name in columns:
        if name in IDENTITY_COLUMNS or name in stage_cols:
            kept.append(name)
        elif name in DROP_REASONS:
            dropped[name] = DROP_REASONS[name]
        elif name.startswith(("asr_", "ocr_", "frame_", "vllm_", "summary_", "postprocess_",
                              "laclau_", "dna_", "sna_", "rdf_", "ep24_")) or name in {
                    "entities", "themes", "positive", "neutral", "negative"}:
            # A producer field the export has not classified yet: refuse to guess. The build
            # fails on the unaccounted list rather than silently dropping a finding.
            continue
        else:
            continue
    return kept, dropped


def unaccounted(columns: Sequence[str], kept: Sequence[str],
                dropped: Mapping[str, str]) -> list[str]:
    known = set(kept) | set(dropped) | set(DERIVED_COLUMNS)
    return [c for c in columns if c not in known]


# --------------------------------------------------------------------------- #
# Child table extraction
# --------------------------------------------------------------------------- #


def _item_rows(items: Iterable[Any], key: str, kind: str) -> Iterator[dict[str, str]]:
    for index, item in enumerate(items):
        if isinstance(item, Mapping):
            yield {
                "record_key": key,
                "item_index": str(index),
                "kind": kind,
                "label": clean_scalar(first_cell({k: str(v) for k, v in item.items()},
                                                 ("label", "name", "text", "actor", "concept",
                                                  "id", "node_id", "entity", "theme", "target")),
                            240),
                "role": clean_scalar(first_cell({k: str(v) for k, v in item.items()},
                                               ("role", "type", "node_type", "edge_type",
                                                "relation_type", "stance", "polarity")), 120),
                "evidence": clean_scalar(first_cell({k: str(v) for k, v in item.items()},
                                                    ("evidence", "quote", "evidence_quote",
                                                     "text", "snippet")), 600),
                "detail": clean_scalar(json.dumps(item, ensure_ascii=False), 1200),
            }
        else:
            yield {
                "record_key": key, "item_index": str(index), "kind": kind,
                "label": clean_scalar(item, 240), "role": "", "evidence": "",
                "detail": "",
            }


def child_rows(row: Mapping[str, str], key: str, stats: CountryStats) -> dict[str, list[dict[str, str]]]:
    """Every one-to-many relation as its own normalized table."""
    def grab(column: str, kind: str, table: str) -> list[dict[str, str]]:
        raw = cell(row, column)
        if not raw or is_empty(raw):
            return []
        items = as_list(raw)
        if not items:
            stats.parse_failures[table] = stats.parse_failures.get(table, 0) + 1
            return []
        return list(_item_rows(items, key, kind))

    entities = grab("postprocess_entities", "entity", "entities")
    entities += grab("entities", "entity_legacy", "entities")
    themes = grab("postprocess_themes", "theme", "entities")
    themes += grab("themes", "theme_legacy", "entities")
    entities += themes
    nodes = grab("sna_nodes_json", "sna_node", "sna_nodes")
    edges = grab("sna_edges_json", "sna_edge", "sna_edges")
    statements = grab("dna_statements_json", "dna_statement", "dna_statements")

    claims: list[dict[str, str]] = []
    structured = parse_json_cell(cell(row, "laclau_structured_json"))
    if isinstance(structured, dict):
        for section, value in structured.items():
            if isinstance(value, list):
                claims.extend(_item_rows(value, key, f"discourse:{section}"))
            elif isinstance(value, (str, int, float)) and str(value).strip():
                claims.append({
                    "record_key": key, "item_index": "0", "kind": f"discourse:{section}",
                    "label": clean_scalar(value, 240), "role": section, "evidence": "",
                    "detail": "",
                })
    elif isinstance(structured, list):
        claims.extend(_item_rows(structured, key, "discourse"))
    elif cell(row, "laclau_structured_json") and not is_empty(cell(row, "laclau_structured_json")) \
            and not structured:
        stats.parse_failures["discourse_claims"] = stats.parse_failures.get("discourse_claims", 0) + 1

    return {
        "entities": entities, "discourse_claims": claims,
        "dna_statements": statements, "sna_nodes": nodes, "sna_edges": edges,
    }


def rdf_rows(row: Mapping[str, str], key: str) -> list[dict[str, str]]:
    status = first_cell(row, STAGE_FIELDS["9_rdf"]["status"])
    path = first_cell(row, STAGE_FIELDS["9_rdf"]["machine"])
    if not status and not path:
        return []
    return [{
        "record_key": key, "rdf_status": status, "resource": path,
        "triples": cell(row, "rdf_triple_count"), "note": cell(row, "rdf_error"),
    }]


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #



#: Columns that indicate "how much of the record the pipeline actually produced", used to choose the
#: most complete row when one video appears several times in a cumulative frame.
def completeness_score(row: Mapping[str, str], profile: str) -> int:
    if profile == "legacy":
        fields: tuple[str, ...] = ("whisper_transcript", "ocr_1", "frame_1", "summary_analysis",
                                   "entities", "topics", "formula_of_populism_analysis",
                                   "manifestoberta_predicted_class")
    else:
        fields = tuple(name for spec in STAGE_FIELDS.values()
                       for group in ("status", "human") for name in spec[group])
    return sum(1 for name in fields if cell(row, name))


def iter_source(source: Path) -> Iterator[tuple[int, dict[str, str]]]:
    """Stream a source CSV with BOM-normalized headers; yield (row_number, row)."""
    with source.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        reader.fieldnames = [name.lstrip("\ufeff") for name in (reader.fieldnames or ())]
        yield from enumerate(reader)


def select_primary_rows(source: Path, country: str, profile: str, limit: int | None,
                        filter_value: str | None,
                        require_video_id: bool = False) -> tuple[dict[str, int], CountryStats]:
    """Pass 1: choose one *most complete* row per identity, and count what was seen.

    Keeping the first occurrence would export a video's early, partly-filled row and understate stage
    coverage; the winner is therefore the row that carries the most stage output.
    """
    stats = CountryStats(country=country, source_path=str(source))
    best: dict[str, tuple[int, int]] = {}
    seen_ids: dict[str, int] = {}
    for number, row in iter_source(source):
        if limit is not None and number >= limit:
            break
        if filter_value is not None and cell(row, "country").lower() != filter_value.lower():
            continue
        stats.rows_read += 1
        key = identity_key(country, row, require_video_id=require_video_id)
        if not key:
            stats.invalid_ids += 1
            continue
        score = completeness_score(row, profile)
        if key in best:
            seen_ids[key] = seen_ids.get(key, 1) + 1
            if score > best[key][0]:
                best[key] = (score, number)
        else:
            best[key] = (score, number)
            seen_ids[key] = 1
    stats.duplicates = sum(count - 1 for count in seen_ids.values())
    return {key: value[1] for key, value in best.items()}, stats


def export_country(country: str, source: Path, output: Path, limit: int | None,
                   manifest_inputs: dict[str, Any], *, profile: str = "reprocessed",
                   filter_value: str | None = None,
                   require_video_id: bool = False) -> CountryStats:
    stats = CountryStats(country=country, source_path=str(source),
                         source_bytes=source.stat().st_size, source_sha256=sha256_file(source))

    winners, pre_stats = select_primary_rows(source, country, profile, limit, filter_value,
                                             require_video_id)
    stats.rows_read = pre_stats.rows_read
    stats.duplicates = pre_stats.duplicates
    stats.invalid_ids = pre_stats.invalid_ids

    with source.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        # A BOM in the first header cell would become a column name no classifier matches.
        reader.fieldnames = [name.lstrip("\ufeff") for name in (reader.fieldnames or ())]
        columns = list(reader.fieldnames or ())
        stats.source_columns = len(columns)
        if profile == "legacy":
            kept, dropped, unknown = classify_legacy(columns)
            stats.unaccounted_columns = unknown
            stats.stage_unavailable = list(STAGE_FIELDS)
        else:
            kept, dropped = classify_columns(columns)
            stats.unaccounted_columns = unaccounted(columns, kept, dropped)
        if profile != "legacy":
            for stage, spec in STAGE_FIELDS.items():
                if not any(name in columns for group in spec.values() for name in group):
                    stats.stage_unavailable.append(stage)

        text_path = output / f"{country}_text.jsonl.gz"
        tables = ("entities", "discourse_claims", "dna_statements", "sna_nodes", "sna_edges")
        writers: dict[str, tuple[Any, csv.DictWriter]] = {}
        for table in tables:
            handle_t = (output / f"{table}.csv").open("w", encoding="utf-8", newline="")
            writer = csv.DictWriter(handle_t, fieldnames=("record_key", "item_index", "kind",
                                                          "label", "role", "evidence", "detail"))
            if country == COUNTRIES[0]:
                writer.writeheader()
            writers[table] = (handle_t, writer)

        rdf_handle = (output / "rdf_resources.csv").open("w", encoding="utf-8", newline="")
        rdf_writer = csv.DictWriter(rdf_handle, fieldnames=("record_key", "rdf_status", "resource",
                                                            "triples", "note"))
        if country == COUNTRIES[0]:
            rdf_writer.writeheader()

        index_name = f"{country}.csv"
        index_handle = (output / index_name).open("w", encoding="utf-8", newline="")
        index_fields = (["record_key", "has_usable_id"] + list(LEGACY_KEEP)
                        if profile == "legacy"
                        else list(IDENTITY_COLUMNS) + list(INDEX_STATUS_COLUMNS)
                        + list(DERIVED_COLUMNS))
        index_writer = csv.DictWriter(index_handle, fieldnames=index_fields, extrasaction="ignore")
        index_writer.writeheader()

        with gzip.open(text_path, "wt", encoding="utf-8") as text_out:
            for number, row in enumerate(reader):
                if limit is not None and number >= limit:
                    break
                if filter_value is not None and cell(row, "country").lower() != filter_value.lower():
                    continue
                key = identity_key(country, row, require_video_id=require_video_id)
                # export only the most complete row for this identity (chosen in pass 1)
                if not key or winners.get(key) != number:
                    continue

                children = child_rows(row, key, stats)
                for table, rows in children.items():
                    handle_t, writer = writers[table]
                    for item in rows:
                        writer.writerow(item)
                    stats.children[table] = stats.children.get(table, 0) + len(rows)
                for item in rdf_rows(row, key):
                    rdf_writer.writerow(item)

                index_row = ({name: clean_scalar(row.get(name, ""), 800) for name in LEGACY_KEEP}
                             if profile == "legacy"
                             else {name: clean_scalar(row.get(name, ""), 800)
                                   for name in IDENTITY_COLUMNS})
                if profile == "legacy":
                    index_row = {"record_key": key, "has_usable_id": "1", **index_row}
                    index_writer.writerow(index_row)
                    stats.rows_exported += 1
                    text_record = {"record_key": key, "country": country, "profile": "legacy"}
                    legacy_block_out = {name: cell(row, name) for name in LEGACY_KEEP
                                        if name not in index_row and cell(row, name)}
                    if legacy_block_out:
                        text_record["legacy"] = legacy_block_out
                    text_out.write(json.dumps(text_record, ensure_ascii=False) + "\n")
                    continue

                index_row.update({name: clean_scalar(row.get(name, ""), 200)
                                  for name in INDEX_STATUS_COLUMNS})
                index_row.update({
                    "record_key": key,
                    "has_usable_id": "1",
                    "entity_count": str(sum(1 for e in children["entities"]
                                           if e["kind"].startswith("entity"))),
                    "theme_count": str(sum(1 for e in children["entities"]
                                           if e["kind"].startswith("theme"))),
                    "discourse_claim_count": str(len(children["discourse_claims"])),
                    "dna_statement_total": str(len(children["dna_statements"])),
                    "sna_node_count": str(len(children["sna_nodes"])),
                    "sna_edge_count": str(len(children["sna_edges"])),
                    "stage_status_summary": ",".join(
                        f"{step}={first_cell(row, spec['status']) or 'absent'}"
                        for step, spec in STAGE_FIELDS.items()
                        if any(name in columns for name in spec["status"])
                    ),
                    "researcher_note": clean_scalar(row.get("researcher_note", ""), 600),
                })
                index_writer.writerow(index_row)
                stats.rows_exported += 1

                for step, spec in STAGE_FIELDS.items():
                    if any(cell(row, name) for name in spec["status"]):
                        stats.stage_records[step] = stats.stage_records.get(step, 0) + 1

                text_record: dict[str, Any] = {"record_key": key, "country": country}
                for step, spec in STAGE_FIELDS.items():
                    block: dict[str, str] = {}
                    for group in ("human", "machine"):
                        for name in spec[group]:
                            value = cell(row, name)
                            if value:
                                block[name] = value
                    if block:
                        text_record[step] = block
                text_out.write(json.dumps(text_record, ensure_ascii=False) + "\n")

        index_handle.close()
        for handle_t, _writer in writers.values():
            handle_t.close()
        rdf_handle.close()

    manifest_inputs[country] = {
        "profile": profile,
        "filter": filter_value,
        "source": stats.source_path, "bytes": stats.source_bytes,
        "sha256": stats.source_sha256, "columns": stats.source_columns,
        "kept_columns": len(kept), "dropped_columns": len(dropped),
        "dropped_reasons": dropped, "stage_unavailable": stats.stage_unavailable,
    }
    return stats


def write_combined(output: Path, countries: Sequence[str]) -> dict[str, int]:
    """Concatenate the per-country index rows into one combined frame (identity preserved).

    Countries may come from different profiles (reprocessed Finland, legacy Poland/Portugal), so the
    combined header is the **union** of their columns: a reprocessed column is empty for a legacy row
    and vice versa. The per-country profile is recorded in the manifest, so an empty cell is never
    mistaken for "the stage ran and found nothing".
    """
    present = [output / f"{country}.csv" for country in countries]
    present = [path for path in present if path.exists()]
    header: list[str] = []
    for path in present:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for name in csv.DictReader(handle).fieldnames or []:
                if name not in header:
                    header.append(name)
    rows = 0
    with (output / "combined.csv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=header, restval="")
        writer.writeheader()
        for path in present:
            with path.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    writer.writerow(row)
                    rows += 1
    return {"combined_rows": rows}


def write_text_bundle(output: Path, countries: Sequence[str]) -> None:
    with gzip.open(output / "text.jsonl.gz", "wt", encoding="utf-8") as out:
        for country in countries:
            path = output / f"{country}_text.jsonl.gz"
            if not path.exists():
                continue
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    out.write(line)


def write_manifest(output: Path, stats: Sequence[CountryStats], inputs: Mapping[str, Any],
                   generated_at: str) -> None:
    total = sum(s.rows_exported for s in stats)
    coverage = {}
    for stat in stats:
        # "0 records" and "this source has no such stage" are different findings: an unavailable
        # stage must never read as a stage that ran and produced nothing.
        coverage[stat.country] = {
            step: ({"records": 0, "available": False,
                    "reason": "stage not present in this source (legacy/pre-Roihu frame)",
                    "pct_of_exported": 0.0}
                   if step in stat.stage_unavailable else
                   {"records": stat.stage_records.get(step, 0), "available": True,
                    "pct_of_exported": round(100 * stat.stage_records.get(step, 0)
                                             / stat.rows_exported, 1)
                    if stat.rows_exported else 0.0})
            for step in STAGE_FIELDS
        }
    manifest = {
        "builder_version": BUILDER_VERSION,
        "generated_at": generated_at,
        "inputs": inputs,
        "record_counts": {
            "exported_total": total,
            **{s.country: {"read": s.rows_read, "exported": s.rows_exported,
                           "duplicates": s.duplicates, "invalid_ids": s.invalid_ids}
               for s in stats},
        },
        "stage_coverage": coverage,
        "children": {s.country: s.children for s in stats},
        "parse_failures": {s.country: s.parse_failures for s in stats},
        "unaccounted_source_columns": {s.country: s.unaccounted_columns for s in stats},
        "outputs": {p.name: p.stat().st_size for p in sorted(output.iterdir()) if p.is_file()},
    }
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")


def write_qa(output: Path, stats: Sequence[CountryStats]) -> None:
    lines = ["# EP24 export — QA and coverage report", ""]
    lines.append(f"Generated by `{BUILDER_VERSION}`. Coverage is measured, never assumed: a stage "
                 "with no status column for a country is reported as **unavailable**, not as zero "
                 "records.")
    lines.append("")
    lines.append("| country | rows read | exported | duplicates | unusable ids | stages available "
                 "| stages unavailable |")
    lines.append("| --- | ---: | ---: | ---: | ---: | --- | --- |")
    for s in stats:
        available = [step for step in STAGE_FIELDS if step not in s.stage_unavailable]
        lines.append(f"| {s.country} | {s.rows_read} | {s.rows_exported} | {s.duplicates} | "
                     f"{s.invalid_ids} | {len(available)} | {', '.join(s.stage_unavailable) or '—'} |")
    lines.append("")
    for s in stats:
        lines.append(f"## {s.country}")
        lines.append("")
        lines.append(f"Source: `{s.source_path}` ({s.source_bytes:,} bytes, "
                     f"sha256 `{s.source_sha256[:16]}…`), {s.source_columns} columns.")
        if s.stage_unavailable and len(s.stage_unavailable) == len(STAGE_FIELDS):
            lines.append("")
            lines.append("**Profile: legacy schema.** This source is the pre-Roihu 75-column "
                         "dashboard export: it carries the legacy transcript/OCR/summary/entities "
                         "fields and *none* of the reprocessed steps. Every reprocessed stage is "
                         "reported as unavailable rather than as zero records.")
        lines.append("")
        lines.append("| stage | records | % of exported |")
        lines.append("| --- | ---: | ---: |")
        for step in STAGE_FIELDS:
            if step in s.stage_unavailable:
                lines.append(f"| {step} | — | unavailable |")
                continue
            count = s.stage_records.get(step, 0)
            pct = (100 * count / s.rows_exported) if s.rows_exported else 0.0
            lines.append(f"| {step} | {count} | {pct:.1f} % |")
        lines.append("")
        if s.children:
            lines.append("Child rows: " + ", ".join(f"{k}={v}" for k, v in sorted(s.children.items())))
            lines.append("")
        if s.parse_failures:
            lines.append("Unparseable JSON cells (kept in the text bundle, excluded from the child "
                         "table): " + ", ".join(f"{k}={v}" for k, v in sorted(s.parse_failures.items())))
            lines.append("")
        if s.unaccounted_columns:
            lines.append("**Unaccounted source columns** (a producer contract change): "
                         + ", ".join(s.unaccounted_columns))
            lines.append("")
        lines.append("A status field proves the stage ran. It does **not** validate the "
                     "interpretation, and a missing stage is never read as \"no phenomenon\".")
        lines.append("")
    (output / "QA_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def write_dictionary(output: Path) -> None:
    lines = ["# EP24 export — data dictionary", "",
             "Every artifact is keyed by `record_key` (`country/video_id`).", "",
             "## Files", "",
             "| file | shape | meaning |", "| --- | --- | --- |",
             ("| `combined.csv`, `<country>.csv` | one row per video | identity, stage statuses, "
             "derived counts; the researcher-facing table |"),
             ("| `text.jsonl.gz`, `<country>_text.jsonl.gz` | one JSON object per video | the "
             "human-readable and machine-readable output of every stage, keyed by step |"),
             ("| `entities.csv` | one row per entity/theme mention | `kind` distinguishes model "
             "(step 5) from legacy entity columns |"),
             ("| `discourse_claims.csv` | one row per Laclau/Palonen coding section or statement | "
             "model-coded hypotheses, traceable to the record |"),
             ("| `dna_statements.csv` | one row per actor–concept statement | Step 7, evidence quote "
             "in `evidence` when the producer supplies one |"),
             ("| `sna_nodes.csv`, `sna_edges.csv` | one row per node/edge | Step 8 empirical graph; "
             "actor–actor only when the producer emitted an edge |"),
             ("| `rdf_resources.csv` | one row per record | Step 9 export status/resources, when the "
             "producer writes them into the frame (Step 9 is otherwise file-based) |"),
             ("| `MANIFEST.json` | — | source hashes, row counts, stage coverage, kept/dropped "
             "columns with reasons |"),
             "| `QA_REPORT.md` | — | what is present, what is missing, what failed to parse |", "",
             "## Derived columns", "", "| column | meaning |", "| --- | --- |"]
    lines += [f"| `{name}` | {reason} |" for name, reason in DERIVED_COLUMNS.items()]
    lines += ["", "## Dropped columns and why", "", "| column | reason |", "| --- | --- |"]
    lines += [f"| `{name}` | {reason} |" for name, reason in sorted(DROP_REASONS.items())]
    lines += ["", ("Dropping a backend payload is not a data loss: prompt contexts, retrieval "
              "payloads, hashes and telemetry are regenerable, and every *finding* they inform is "
              "kept in its own stage block.")]
    (output / "DATA_DICTIONARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_sources(pairs: Sequence[str]) -> dict[str, tuple[Path, str | None]]:
    """``country=path`` or ``country=path:profile`` (a per-source profile override)."""
    sources: dict[str, tuple[Path, str | None]] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--source expects country=path, got {pair!r}")
        country, path = pair.split("=", 1)
        country = country.strip().lower()
        if country not in COUNTRIES:
            raise SystemExit(f"unknown country {country!r}; expected one of {COUNTRIES}")
        profile: str | None = None
        for candidate in ("reprocessed", "legacy"):
            if path.endswith(f":{candidate}"):
                path, profile = path[: -len(candidate) - 1], candidate
        sources[country] = (Path(path).expanduser(), profile)
    return sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export EP24 results for the visualization demo")
    parser.add_argument("--source", action="append", default=[], metavar="COUNTRY=PATH",
                        help="cumulative CSV per country; repeat for each country")
    parser.add_argument("--output", required=False, default="ep24_export",
                        help="output directory (never a source directory)")
    parser.add_argument("--limit", type=int, default=None,
                        help="read at most N rows per country (development subset)")
    parser.add_argument("--profile", choices=("reprocessed", "legacy"), default="reprocessed",
                        help="reprocessed = Roihu cumulative frame; legacy = the 75-column "
                             "pre-Roihu export (reports every reprocessed stage as unavailable)")
    parser.add_argument("--filter-country", action="append", default=[], metavar="COUNTRY=VALUE",
                        help="keep only rows whose in-file country equals VALUE "
                             "(a shared legacy file may hold many countries)")
    parser.add_argument("--require-video-id", action="store_true", default=False,
                        help="treat a row without video_id/_storage_id as unusable even when it "
                             "carries a media key (the historical export_demo contract)")
    parser.add_argument("--fail-on-unaccounted", action="store_true", default=True,
                        help="fail when a producer column is neither kept nor dropped (default)")
    parser.add_argument("--allow-unaccounted", dest="fail_on_unaccounted", action="store_false")
    args = parser.parse_args(argv)

    sources = parse_sources(args.source)
    if not sources:
        raise SystemExit("at least one --source COUNTRY=PATH is required")
    output = Path(args.output).expanduser().resolve()
    for country, (path, _profile) in sources.items():
        if not path.exists():
            raise SystemExit(f"source for {country} does not exist: {path}")
        if output == path.parent.resolve():
            raise SystemExit("refusing to write into the source directory")

    output.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    filters = dict(pair.split("=", 1) for pair in args.filter_country) if args.filter_country else {}
    filters = {k.strip().lower(): v.strip() for k, v in filters.items()}
    inputs: dict[str, Any] = {}
    stats = [export_country(country, path, output, args.limit, inputs,
                            profile=(profile or args.profile),
                            filter_value=filters.get(country),
                            require_video_id=args.require_video_id)
             for country, (path, profile) in sources.items()]

    combined = write_combined(output, [c for c in COUNTRIES if c in sources])
    write_text_bundle(output, [c for c in COUNTRIES if c in sources])
    write_manifest(output, stats, inputs, generated_at)
    write_qa(output, stats)
    write_dictionary(output)

    print(f"exported {sum(s.rows_exported for s in stats)} records from "
          f"{len(sources)} country source(s) -> {output}")
    print(f"combined.csv rows: {combined['combined_rows']}")
    for stat in stats:
        print(f"  {stat.country}: {stat.rows_exported} rows, duplicates {stat.duplicates}, "
              f"unusable ids {stat.invalid_ids}, unavailable stages {stat.stage_unavailable or '—'}")
        if stat.unaccounted_columns:
            print(f"    unaccounted columns: {stat.unaccounted_columns}")
    if args.fail_on_unaccounted and any(s.unaccounted_columns for s in stats):
        print("ERROR: unaccounted source columns — classify them in DROP_REASONS or STAGE_FIELDS",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
