"""Typed, versioned EP24 reprocessed-pipeline view model (issue #177, step 1).

This module is the *visualization-side* contract for the nine-step EP24 reprocessed
pipeline. It exists because the sibling analysis repository owns a machine-readable
stage contract (`ep24_stage_contract.py`, ``STAGE_CONTRACT``) and this repository may
**not** import sibling implementation internals (AGENTS.md rule 2). The field names
below were therefore read from that contract and re-declared here as a consumption
contract, with the provenance of that reading recorded in
``docs/EP24_PIPELINE_FIELD_MAPPING.md``.

Two properties matter more than the rest, and both are enforced by tests rather than
asserted in prose:

* **Nothing is invented.** A field the pipeline does not emit reads as absent. In
  particular **Step 8 emits no status column at all** and **Step 9 emits RDF rather
  than dataframe columns**, so neither can be given a status the data does not carry.
* **The human and machine columns never merge.** ``entities`` / ``themes`` are human
  columns; ``postprocess_entities`` / ``postprocess_themes`` are machine columns. They
  are surfaced separately and are never combined into one "entities" view.

The module is descriptive: it classifies what a row already says. It performs no
discourse analysis, no inference and no scoring, and it reaches no network service.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

#: Bump when the shape of the view model changes.
EP24_VIEW_MODEL_VERSION = "ep24-pipeline-view-v1"

#: The canonical source columns every stage must still be carrying at the end.
#: Re-declared from the analysis contract; this repository does not import it.
SOURCE_COLUMNS: tuple[str, ...] = (
    "country",
    "author_username",
    "account_type",
    "source_type",
    "source_recording",
    "video_id",
    "sequence_number",
    "political_preference",
    "allas_filename",
    "entities",
    "themes",
    "video_duration",
    "researcher_note",
)

#: Stable pipeline identity added by the bootstrap. ``_storage_id`` is the durable
#: handle across Mongo/CSV boundaries; ``video_id`` is the legacy stable source key.
BOOTSTRAP_ADDED_COLUMNS: tuple[str, ...] = ("_storage_id",)

#: The human columns. Machine counterparts live under a ``postprocess_`` prefix and must
#: never be merged with these.
HUMAN_ANNOTATION_COLUMNS: tuple[str, ...] = ("entities", "themes", "researcher_note")

#: The machine counterparts, kept visibly separate.
MACHINE_ANNOTATION_COLUMNS: tuple[str, ...] = (
    "postprocess_entities",
    "postprocess_themes",
    "ep24_entity_canonical_names",
    "ep24_theme_canonical_names",
)


class StageStatus(str, Enum):
    """What a row reports about one stage. A description of the record, not a judgement."""

    #: The stage reports success.
    COMPLETE = "complete"
    #: The stage reports a failure.
    FAILED = "failed"
    #: The stage reports something non-empty that this module does not classify.
    #: ``raw`` on the cell keeps the original string, so nothing is lost by not knowing.
    REPORTED_OTHER = "reported_other"
    #: A status column exists but is empty for this row.
    MISSING = "missing"
    #: The stage exposes no status column at all (Step 8). Absence, recorded honestly.
    NO_STATUS_COLUMN = "no_status_column"
    #: The stage does not write dataframe columns (Step 9 emits RDF artifacts).
    NOT_EXPORTED = "not_exported"


#: Status strings seen across the pipeline's own reports, mapped to a coarse class.
#: Anything else becomes :attr:`StageStatus.REPORTED_OTHER` rather than being guessed at.
_COMPLETE_TOKENS = frozenset({"ok", "success", "succeeded", "complete", "completed", "done"})
_FAILED_TOKENS = frozenset({"fail", "failed", "failure", "error", "errored"})


@dataclass(frozen=True)
class EP24Stage:
    """One numbered pipeline stage, as this repository consumes it."""

    number: int
    key: str
    label: str
    #: The dataframe column carrying this stage's status, if it has one.
    status_column: str | None
    #: Columns holding the stage's evidence or human-readable output.
    evidence_columns: tuple[str, ...] = ()
    #: Columns holding the stage's machine-readable output (JSON strings).
    output_columns: tuple[str, ...] = ()
    #: False for a stage that emits no dataframe columns (Step 9).
    writes_dataframe_columns: bool = True
    notes: str = ""

    def reported_columns(self) -> tuple[str, ...]:
        return (self.evidence_columns + self.output_columns
                + ((self.status_column,) if self.status_column else ()))


def _stage(number, key, label, status_column, evidence=(), outputs=(), writes=True, notes=""):
    return EP24Stage(number=number, key=key, label=label, status_column=status_column,
                     evidence_columns=tuple(evidence), output_columns=tuple(outputs),
                     writes_dataframe_columns=writes, notes=notes)


#: The nine numbered stages. Step 0 (ingestion) is represented separately by
#: :data:`STEP_ZERO_COLUMNS`, because it establishes identity rather than analysing.
EP24_STAGES: tuple[EP24Stage, ...] = (
    _stage(1, "preprocess", "Preprocess (ASR / OCR / frame)", "preprocess_status",
           evidence=("frame_file", "frame_timestamp_seconds", "ocr_1", "asr_transcript",
                     "asr_language", "asr_translated", "video_duration_seconds"),
           outputs=("ocr_runtime_ms", "asr_runtime_ms"),
           notes="One keyframe/OCR at original t=1.0s; ASR is backend-neutral."),
    _stage(2, "frame", "Frame VLM analysis", "frame_analysis_status",
           evidence=("frame_analysis_1", "frame_analysis_timestamp_seconds",
                     "frame_quality_status", "frame_quality_reason"),
           outputs=("frame_analysis_model", "frame_analysis_context_sha256"),
           notes="Also writes the shared processing_status columns."),
    _stage(3, "video", "Whole-video VLM analysis", "vllm_video_status",
           evidence=("vllm_video_analysis", "vllm_video_markdown_analysis",
                     "vllm_video_structured_json", "SCROLL", "SCROLL_SECONDS",
                     "needs_resplit", "video_quality_status", "video_quality_reason"),
           outputs=("vllm_video_model", "vllm_video_prompt_version", "vllm_video_sha256",
                    "vllm_video_runtime_seconds", "vllm_video_structured_output_status"),
           notes="Experimental; the scroll interval of ep24_video.py is excluded from input."),
    _stage(4, "summary", "Multimodal summary / fusion", "summary_quality_status",
           evidence=("summary_analysis", "summary_summary_md", "summary_quality_reason"),
           outputs=("metadata",),
           notes="Evidence-preserving fusion of transcript/OCR/frame/video."),
    _stage(5, "postprocess", "Structured postprocess (entity/theme/sentiment)",
           "processing_status",
           evidence=("postprocess_entities", "postprocess_themes", "postprocess_summary_md",
                     "positive", "neutral", "negative", "processing_status_reason"),
           outputs=("ep24_entity_resolution_json", "ep24_entity_ids",
                    "ep24_codebook_fingerprint", "ep24_memory_entity_ids",
                    "ep24_memory_topic_ids",
                    "ep24_memory_theme_ids",
                    "ep24_sentiment_targets_json",
                    "ep24_memory_sentiment_target_ids_json"),
           notes="Machine columns are separate from the immutable human entities/themes."),
    _stage(6, "discourse_analysis", "Laclau/Palonen discourse analysis", "laclau_status",
           evidence=("formula_of_populism_analysis", "formula_of_populism_us",
                     "formula_of_populism_frontier", "laclau_summary_md",
                     "laclau_abstention_reason", "laclau_error"),
           outputs=("laclau_structured_json", "laclau_formula_conditions_met",
                    "laclau_prompt_version", "laclau_model_metadata_json",
                    "laclau_context_sha256", "laclau_generated_at"),
           notes="Descriptive output; abstention is a first-class value, not a failure."),
    _stage(7, "discourse_network_analysis", "Leifeld discourse network analysis (DNA)",
           "dna_status",
           evidence=("dna_analysis_markdown", "dna_statements_json", "dna_error"),
           outputs=("dna_statement_count", "dna_binary_count", "dna_uncertain_count",
                    "dna_actor_unresolved_count", "dna_concept_novel_count",
                    "dna_prompt_version", "dna_generated_at"),
           notes="One actor-concept statement per row of dna_statements_json."),
    _stage(8, "social_network_analysis", "Social network analysis (SNA)",
           None,  # <- Step 8 writes no status column. This absence is deliberate and honest.
           evidence=("sna_analysis_markdown", "sna_edges_json"),
           notes="No status column is emitted; status is inferred from artifact presence "
                 "and is labelled derived. DNA congruence is never treated as a social tie."),
    _stage(9, "rdf", "RDF / knowledge-graph export", None, writes=False,
           notes="Deterministic CPU export producing graph.nt / graph.ttl artifacts, "
                 "not dataframe columns."),
)

#: Columns that establish Step 0 identity during ingestion.
STEP_ZERO_COLUMNS: tuple[str, ...] = ("country", "video_id", "allas_filename",
                                     "source_type", "account_type") + BOOTSTRAP_ADDED_COLUMNS

#: Stages keyed by number, for callers that address a stage the way the issue does.
STAGES_BY_NUMBER: dict[int, EP24Stage] = {stage.number: stage for stage in EP24_STAGES}


def classify_status_value(raw: Any) -> StageStatus:
    """Coarse classification of one reported status string.

    Unknown non-empty values become :attr:`StageStatus.REPORTED_OTHER` — the module does
    not guess, and the caller keeps ``raw`` so nothing is discarded.
    """
    text = "" if raw is None else str(raw).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return StageStatus.MISSING
    lowered = text.casefold()
    if lowered in _COMPLETE_TOKENS:
        return StageStatus.COMPLETE
    if lowered in _FAILED_TOKENS:
        return StageStatus.FAILED
    return StageStatus.REPORTED_OTHER


@dataclass(frozen=True)
class StageReport:
    """One stage's state for one document. ``raw`` is always preserved."""

    number: int
    key: str
    status: StageStatus
    raw: str = ""
    #: True when the stage produced at least one non-empty value in this row.
    has_output: bool = False
    derived: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "key": self.key,
            "status": self.status.value,
            "raw": self.raw,
            "has_output": self.has_output,
            "derived": self.derived,
        }


def _cell(row: Mapping[str, Any], column: str | None) -> str:
    if not column:
        return ""
    value = row.get(column, "")
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "<na>"} else text


def _has_any(row: Mapping[str, Any], columns: tuple[str, ...]) -> bool:
    return any(_cell(row, column) for column in columns)


def stage_report(row: Mapping[str, Any], stage: EP24Stage) -> StageReport:
    """Report one stage's state for one row, without inventing anything.

    * A stage with a status column is classified from that column.
    * A stage with **no** status column (Step 8) is read from its artifacts, and the
      result is marked ``derived=True`` so a UI can label it as inferred.
    * A stage that writes no dataframe columns (Step 9) reports ``NOT_EXPORTED``.
    """
    if not stage.writes_dataframe_columns:
        return StageReport(stage.number, stage.key, StageStatus.NOT_EXPORTED)
    if stage.status_column is None:
        produced = _has_any(row, stage.evidence_columns) or _has_any(row, stage.output_columns)
        return StageReport(stage.number, stage.key,
                           StageStatus.COMPLETE if produced else StageStatus.MISSING,
                           derived=True)
    raw = _cell(row, stage.status_column)
    return StageReport(
        stage.number,
        stage.key,
        classify_status_value(raw),
        raw=raw,
        has_output=_has_any(row, stage.evidence_columns) or _has_any(row, stage.output_columns),
    )


@dataclass(frozen=True)
class EP24DocumentView:
    """One EP24 document, as the dashboard needs it: identity first, then stage reports."""

    view_model_version: str
    #: Stable identity. ``storage_id`` is the durable handle; ``video_id`` the legacy key.
    storage_id: str
    video_id: str
    country: str
    identity_aliases: tuple[str, ...]
    stages: tuple[StageReport, ...]
    #: Human and machine annotations are carried separately on purpose.
    human_annotations: dict[str, str]
    machine_annotations: dict[str, str]

    def stage(self, number: int) -> StageReport:
        for report in self.stages:
            if report.number == number:
                return report
        raise KeyError(f"no stage {number} in this view")

    def completed_steps(self) -> tuple[int, ...]:
        return tuple(r.number for r in self.stages if r.status is StageStatus.COMPLETE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "view_model_version": self.view_model_version,
            "storage_id": self.storage_id,
            "video_id": self.video_id,
            "country": self.country,
            "identity_aliases": list(self.identity_aliases),
            "stages": [r.to_dict() for r in self.stages],
            "human_annotations": dict(self.human_annotations),
            "machine_annotations": dict(self.machine_annotations),
        }


def normalize_document(row: Mapping[str, Any]) -> EP24DocumentView:
    """Build the view model for one pipeline row.

    Identity is taken from ``_storage_id`` and ``video_id``. Every other identifier the
    row happens to carry is kept as an *alias*, never promoted into the identity path
    (AGENTS.md rule 4 / serialization rule "backend-specific IDs must never enter the
    canonical identity path").
    """
    storage_id = _cell(row, "_storage_id")
    video_id = _cell(row, "video_id")
    aliases = tuple(
        value
        for value in (
            _cell(row, "allas_filename"),
            _cell(row, "author_username"),
            _cell(row, "source_recording"),
        )
        if value
    )
    return EP24DocumentView(
        view_model_version=EP24_VIEW_MODEL_VERSION,
        storage_id=storage_id,
        video_id=video_id,
        country=_cell(row, "country"),
        identity_aliases=aliases,
        stages=tuple(stage_report(row, stage) for stage in EP24_STAGES),
        human_annotations={c: _cell(row, c) for c in HUMAN_ANNOTATION_COLUMNS},
        machine_annotations={c: _cell(row, c) for c in MACHINE_ANNOTATION_COLUMNS},
    )


@dataclass
class PipelineOverview:
    """Per-stage counts across a document set. Descriptive only."""

    documents: int = 0
    by_stage: dict[int, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "view_model_version": EP24_VIEW_MODEL_VERSION,
            "documents": self.documents,
            "by_stage": {str(k): dict(sorted(v.items())) for k, v in sorted(self.by_stage.items())},
        }


def pipeline_overview(rows: Any) -> PipelineOverview:
    """Count stage states over an iterable of row mappings.

    A stage that reports ``no_status_column`` or ``not_exported`` is counted under that
    key, so the overview cannot imply a completion the pipeline never recorded.
    """
    overview = PipelineOverview()
    for row in rows:
        overview.documents += 1
        for stage in EP24_STAGES:
            report = stage_report(row, stage)
            bucket = overview.by_stage.setdefault(stage.number, {})
            bucket[report.status.value] = bucket.get(report.status.value, 0) + 1
    return overview


def combined_columns() -> tuple[str, ...]:
    """Every dataframe column this view model reads, in stage order.

    Useful for a preflight check: a dashboard pointed at a stale export can compare the
    columns it found against this list and report what is genuinely absent rather than
    rendering blanks.
    """
    columns: list[str] = list(SOURCE_COLUMNS) + list(BOOTSTRAP_ADDED_COLUMNS)
    for stage in EP24_STAGES:
        for column in stage.reported_columns():
            if column not in columns:
                columns.append(column)
    return tuple(columns)


def missing_columns(present: Any) -> tuple[str, ...]:
    """Which expected columns a given column set does not have. Reported, never faked."""
    have = set(present)
    return tuple(column for column in combined_columns() if column not in have)
