# EP24 reprocessed pipeline — field mapping, identity and provenance contract

**Status:** research-visualization contract for issue [#177](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/issues/177). Descriptive only: it records what the pipeline already emits. It defines no rule, and it performs no analysis.

**Provenance of this mapping.** Every field name below was read from the **current** EP24 analysis code, not assumed from the legacy dashboard. The authoritative source is `ep24_stage_contract.py` (`STAGE_CONTRACT`, issue #64) in [LaclauGPT-Multimodal-Analysis](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis), read at commit `1efcf86`. Per this repository's AGENTS.md rule 2 (*do not import sibling implementation internals*) that contract is **re-declared**, not imported; the consuming code is `src/laclaugpt_visualization/ep24_pipeline.py` and the two must be compared by hand when the sibling changes.

> **The old `ep2024_dashboard` columns are archaeology.** They are a compatibility reference (see [LEGACY_DASHBOARD_AUDIT.md](LEGACY_DASHBOARD_AUDIT.md)), never the current contract.

---

## 1. Step numbering

The issue's numbering is confirmed against the live code: **Step 0 is ingestion; Steps 1–9 are the numbered analysis/export stages**, one batch entry point each (`step_N_roihu_*.py`). Step 3 (whole-video VLM) is reserved even while experimental, so later numbers stay stable.

| Step | Stage key | Entry point | GPU | Writes dataframe columns |
| ---: | --- | --- | --- | --- |
| 0 | ingestion | `step_0_roihu_import.py` | no | identity only |
| 1 | `preprocess` | `step_1_roihu_preprocess.py` | yes | yes |
| 2 | `frame` | `step_2_roihu_frame.py` | yes | yes |
| 3 | `video` | `step_3_roihu_video.py` | yes | yes |
| 4 | `summary` | `step_4_roihu_summary.py` | yes | yes |
| 5 | `postprocess` | `step_5_roihu_postprocess.py` | yes | yes |
| 6 | `discourse_analysis` | `step_6_roihu_discourse_analysis.py` | yes | yes |
| 7 | `discourse_network_analysis` | `step_7_roihu_discourse_network_analysis.py` | yes | yes |
| 8 | `social_network_analysis` | `step_8_roihu_social_network_analysis.py` | yes | yes |
| 9 | `rdf` | `step_9_roihu_rdf.py` | **no** (deterministic CPU export) | **no — emits RDF** |

---

## 2. Source and identity columns (Step 0)

Carried by every row and preserved by every stage:

```
country, author_username, account_type, source_type, source_recording,
video_id, sequence_number, political_preference, allas_filename,
entities, themes, video_duration, researcher_note
+ _storage_id        (added by the bootstrap)
```

### Identity contract

| Role | Column | Rule |
| --- | --- | --- |
| **Durable handle** | `_storage_id` | primary across Mongo/CSV boundaries |
| **Legacy stable source key** | `video_id` | primary for source identity and joins |
| **Country namespace** | `country` | every join that can mix countries must be keyed within a country |
| Aliases (never identity) | `allas_filename`, `author_username`, `source_recording` | displayed, **never** used as a join key |
| Implementation details (never identity) | Mongo `_id`, SQLite PK, row index | must not enter the identity path |

**No cross-country joins.** `video_id` is stable *within* a country; Finland, Poland and Portugal rows must not be joined on it alone. The view model exposes `country` alongside identity for exactly this reason.

---

## 3. Per-step fields

Only the **status / evidence / machine-output** columns the dashboard needs are listed. A stage appends many more columns; the full tuple is in `ep24_pipeline.EP24_STAGES`.

### Step 1 — `preprocess`
- **Status:** `preprocess_status`, plus `preprocess_note`, `preprocess_completed_at`
- **Evidence:** `frame_file`, `frame_timestamp_seconds`, `ocr_1`, `asr_transcript`, `asr_language`, `asr_translated`, `video_duration_seconds`
- **Machine:** `ocr_backend`, `ocr_model`, `ocr_runtime_ms`, `asr_backend`, `asr_model`, `asr_runtime_ms`
- **Note:** exactly **one** keyframe/OCR at original `t = 1.0 s`. The EP24 scroll artifact (`ep24_video.py`) is excluded from ASR, frames, OCR and embeddings, so a frame at t=1.0 must not be read as content.

### Step 2 — `frame`
- **Status:** `frame_analysis_status` (+ the shared `processing_status`)
- **Evidence:** `frame_analysis_1`, `frame_analysis_timestamp_seconds`, `frame_quality_status`, `frame_quality_reason`
- **Machine:** `frame_analysis_model`, `frame_analysis_context_sha256`

### Step 3 — `video` (whole-video VLM)
- **Status:** `vllm_video_status` (+ `processing_status`)
- **Evidence:** `vllm_video_analysis`, `vllm_video_markdown_analysis`, `vllm_video_structured_json`, `SCROLL`, `SCROLL_SECONDS`, `needs_resplit`, `video_quality_status`, `video_quality_reason`
- **Machine (selection):** `vllm_video_model`, `vllm_video_prompt_version`, `vllm_video_prompt_sha256`, `vllm_video_sha256`, `vllm_video_runtime_seconds`, `vllm_video_structured_output_status`, `vllm_gpu_name`, `vllm_peak_gpu_memory_mb`
- **Note:** `SCROLL` / `needs_resplit` are **data-quality** signals, not content. Additional scrolls mean a re-split, not a finding.

### Step 4 — `summary`
- **Status:** `summary_quality_status` (+ `processing_status`)
- **Evidence:** `summary_analysis`, `summary_summary_md`, `summary_quality_reason`
- **Machine:** `metadata`

### Step 5 — `postprocess`
- **Status:** `processing_status`, `processing_status_reason`
- **Evidence:** `postprocess_entities`, `postprocess_themes`, `postprocess_summary_md`, `positive`, `neutral`, `negative`
- **Machine:** `ep24_entity_resolution_json`, `ep24_entity_ids`, `ep24_entity_canonical_names`, `ep24_entity_unresolved_json`, `ep24_codebook_fingerprint`, `ep24_codebook_context_json`, `ep24_theme_resolution_json`, `ep24_theme_canonical_names`, `ep24_sentiment_targets_json`, `ep24_memory_*`, `ep24_seed_*`
- **Boundary:** `postprocess_entities` / `postprocess_themes` are **machine**; `entities` / `themes` are the **immutable human** columns. They must be shown separately and never merged into one "entities" view.

### Step 6 — `discourse_analysis` (Laclau / Palonen)
- **Status:** `laclau_status`, `laclau_error`
- **Evidence:** `formula_of_populism_analysis`, `formula_of_populism_us`, `formula_of_populism_frontier`, `laclau_summary_md`, `laclau_abstention_reason`
- **Machine:** `laclau_structured_json`, `laclau_formula_conditions_met`, `laclau_prompt_version`, `laclau_model_metadata_json`, `laclau_context_sha256`, `laclau_context_truncated`, `laclau_codebook_fingerprint`, `laclau_generated_at`, `laclau_persistence_status`
- **Boundary:** **abstention is a first-class value**, not a failure. `laclau_formula_conditions_met` and `laclau_abstention_reason` must be visible, never rendered as "no data". Per AGENTS.md's epistemic boundary, frequency or co-occurrence never establishes a nodal signifier, an antagonistic frontier, equivalence or hegemony.

### Step 7 — `discourse_network_analysis` (Leifeld DNA)
- **Status:** `dna_status`, `dna_error`
- **Evidence:** `dna_analysis_markdown`, `dna_statements_json` (one actor–concept/position statement per entry, with an explicit support/oppose/uncertain qualifier), `dna_statement_count`, `dna_binary_count`, `dna_uncertain_count`, `dna_actor_unresolved_count`, `dna_concept_novel_count`
- **Machine:** `dna_prompt_version`, `dna_model_metadata_json`, `dna_context_sha256`, `dna_context_truncated`, `dna_codebook_fingerprint`, `dna_generated_at`, `dna_persistence_status`
- **Boundary:** actor↔concept statements only. Any actor↔actor projection must be labelled **derived** and traceable to its constituent statements; a topic mention is not a position.

### Step 8 — `social_network_analysis` (SNA)
- **Status:** **none — the stage emits no status column.** The view model therefore reports a status **derived from artifact presence** and marks it `derived=True` so the UI can label it as inferred. This is the single most important honest absence in the mapping.
- **Evidence:** `sna_analysis_markdown`, `sna_edges_json` (empirically evidenced actor↔actor ties)
- **Boundary:** **empty graphs and no-evidence states are normal.** DNA congruence is never a social tie; the Castells/communication-power reading is a separate interpretation and must be visibly separate from the empirical graph.

### Step 9 — `rdf`
- **Status:** not a column. The stage is a deterministic CPU export producing `graph.nt` / `graph.ttl`.
- The view model reports `not_exported` for the dataframe and expects the dashboard to report export status from the **artifact**, its projection provenance and its validation warnings.

---

## 4. Status semantics

`ep24_pipeline.classify_status_value` maps a reported string to a coarse class:

| Class | Meaning |
| --- | --- |
| `complete` | the pipeline reports success (`ok`, `success`, `complete`, `done`, …) |
| `failed` | the pipeline reports a failure (`failed`, `error`, …) |
| `reported_other` | a non-empty value this module does not classify — **the raw string is preserved** |
| `missing` | the status column exists but is empty for this row |
| `no_status_column` | the stage exposes no status column (Step 8) |
| `not_exported` | the stage writes no dataframe columns (Step 9) |

An unrecognised value is never guessed at. It is classified as `reported_other` **and its original text is kept**, so a new upstream value appears as a visible unknown rather than a silent success.

**`exit 0` from Slurm is not a scientific-quality claim.** Step status is operational provenance only.

---

## 5. Provenance classes the dashboard must keep apart

| Class | Where it comes from |
| --- | --- |
| **Human/researcher** | `entities`, `themes`, `researcher_note` (immutable human annotation) |
| **Model-generated** | every `postprocess_*`, `laclau_*`, `dna_*`, `sna_*`, `vllm_*`, `summary_*`, `frame_analysis_*` value |
| **Source-derived** | `asr_transcript`, `ocr_1`, `frame_file`, the frame itself — captured from the source media |
| **Operational** | `*_runtime_ms`, `*_persistence_status`, `vllm_hostname`, `vllm_gpu_name` |

Model-run context that must travel with every generated value: `*_prompt_version`, `*_context_sha256`, `*_codebook_fingerprint`, `*_model_metadata_json`, `*_generated_at`, `*_persistence_status`.

See also [PROVENANCE_CONTRACT.md](PROVENANCE_CONTRACT.md) for the shared analysis/effective-run provenance rules.

---

## 6. What a dashboard may and may not do with this

**May:** display, filter, group, drill through, compare legacy versus reprocessed fields for matched `video_id` *within a country*, and show missingness honestly.

**May not:**

- infer a stage's completion from the presence of an unrelated column;
- merge human and machine annotation columns;
- join across countries on `video_id`;
- render an abstention (Step 6) or an empty graph (Step 8) as an error or as "no data";
- convert `postprocess_*` counts or graph centrality into a theoretical conclusion;
- invent transcript, OCR, frame or media values for a text-only record — missing optional multimodal fields stay **absent**.

---

## 7. Preflight and refresh

`ep24_pipeline.missing_columns(present)` compares a dataset's columns against the full expected set, so a dashboard pointed at a stale export can report **what is genuinely absent** instead of rendering blanks. That is the preflight for refreshing Pouta from a new Roihu export; see [EP24_POUTA.md](EP24_POUTA.md) for the transfer and deployment procedure.

When the sibling's `STAGE_CONTRACT` changes, `ep24_pipeline.EP24_STAGES` must be updated by hand and this document re-verified against it. `combined_columns()` is the single place that enumerates the expected field set.
