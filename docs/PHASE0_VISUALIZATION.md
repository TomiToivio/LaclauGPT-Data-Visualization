# Phase 0 visualization compatibility

This document defines the thin Phase 0 compatibility layer for Data Visualization:
it consumes the minimal MongoDB analysis output Phase 0 produces and offers the
smallest useful display/export path needed to confirm the pipeline works end to end.

It does not pull Phase 1 visualization architecture into the Phase 0 runtime, and it
does not redesign Phase 0 Data Analysis.

---

## 1. Role: a compatibility layer, not a reimplementation

The main manual Phase 0 work belongs in Data Analysis. Visualization consumes the
minimal MongoDB analysis output Phase 0 produces and offers only the smallest useful
display/export path needed to confirm the pipeline works.

Consequences:

- Visualization must not re-derive or reinterpret analysis.
- Visualization must not be required for Phase 0 to be "working" — it is how we
  *verify*, not a pipeline stage.
- Phase 0-specific scaffolding is allowed to be temporary and discardable.

## 2. Expected Phase 0 analysis inputs (read from actual code)

Phase 0 analysis (`LaclauGPT-Data-Analysis`, `phase-0` branch) writes flat documents
to:

```text
laclaugpt2_<project>_scraper_collection      # e.g. laclaugpt2_ai26_scraper_collection
```

This is **not** the Phase 1 collection set (`<project>__records` / `__analyzed` /
`__processing`) that the current AI26 dashboard reads via
`ai26_collection_names()`. The Phase 0 layer must therefore read this collection
explicitly rather than reuse the Phase 1 names.

Fields written by `laclaugpt/laclaugpt_process.py` (verified against the code):

| Field | Written by | Meaning |
| --- | --- | --- |
| `document_id` | preprocess | stable id (sha256 of canonical `source_url`) |
| `source_url` | collection | canonical identity anchor |
| `normalized_text` | preprocess | whitespace/encoding-normalized text |
| `content_hash` | preprocess | text hash |
| `metadata` | preprocess | preserved source metadata (actor, arena, formations, language, ...) |
| `phase0.preprocess.status` | preprocess | `ok` / `error` |
| `phase0.summary.status` | summary | `ok` / `error` |
| `phase0.postprocess.status` | postprocess | `ok` / `error` |
| `phase0.discourse.status` | discourse | `ok` / `error` |
| `phase0_summary_raw` | summary | raw LLM response (retained before validation) |
| `phase0_summary` | summary | parsed summary dict |
| `phase0_summary_validated` | postprocess | validated `DocumentSummary` |
| `phase0_summary_validation_error` | postprocess | validation failure message |
| `phase0_discourse_raw` | discourse | raw LLM response |
| `phase0_discourse` | discourse | candidate relational structures |
| `phase0_ontology` | discourse | graph-friendly projection |
| `updated_at` | every stage | last write timestamp |

Validated summary shape (`laclaugpt_postprocess.DocumentSummary`):
`document_id`, `source_url`, `source_date`, `actor_name`, `title`, `summary`,
`claims[]`, `actors[]`, `entities[]`, `topics[]`, `signifiers[]`, `future_visions[]`,
`governance_positions[]`, `evidence[]`, `uncertainty_notes[]`, `model_metadata`,
`prompt_version`.

Discourse shape (`laclaugpt_discourse`): `signifiers`, `articulations`, `demands`,
`chains_equivalence`, `chains_difference`, `collective_subjects`, `frontiers`,
`affects`, `nodal_point_candidates`, `floating_signifier_candidates`,
`empty_signifier_candidates`, `future_vision_candidates`, `formation_evidence`,
`counter_evidence`, `uncertainty_notes`, `model_metadata`, `prompt_version`.

**These are candidate/provisional structures with evidence and abstention — never
final theoretical results.** The visualization must present them as such (this
already matches the repo's existing epistemic rules in `AGENTS.md`).

## 3. Minimal useful path

One explicit, inspectable path — deliberately small:

```
laclaugpt2_<project>_scraper_collection (MongoDB)
        ↓  read (direct, no hidden transformation)
Phase 0 view: list/filter analyzed documents
        ↓
inspect one document: summary + discourse candidates + stage status
        ↓
simple export (JSONL) for debugging or lightweight presentation
```

Defined scope:

1. **List/filter analyzed documents** — by stage status, date, arena and free text,
   over the fields above. Reuse the existing `filter_frame`/`normalize_frame` helpers
   rather than adding a parallel data layer.
2. **Inspect one document** — `phase0_summary_validated`, `phase0_discourse`, the
   `phase0.*.status` markers, and the retained raw response when validation failed
   (that is the debugging hook the Phase 0 design deliberately keeps).
3. **Basic time filtering** — on `source_date`, since Phase 0 has no run model.
4. **Actor/entity/signifier summaries** — only where the fields already exist in
   Phase 0 output. Do not compute new analytical aggregates.
5. **Simple export** — JSONL of the same view, for debugging and lightweight
   presentation.

Explicitly out of scope: graphs, RAG views, validation UI, DNA/SNA, temporal graph
exploration, plugin surfaces.

## 4. Runtime constraints

Phase 0 visualization must require **MongoDB only**:

- no Redis (the existing AI26 dashboard imports `redis` on two paths and must not be
  the Phase 0 path);
- no Allas/S3;
- no multimodal assets;
- no distributed orchestration;
- no Phase 1 graph infrastructure or plugin system;
- no hidden transformations between Analysis and Visualization.

Errors must be obvious: a missing required field (e.g. no `source_url`, or a document
with no `phase0_summary_validated`) should say so plainly rather than render an empty
view.

## 5. Suggested shape (implementation, when requested)

Small and explicit, following the repo's existing structure:

- `src/laclaugpt_visualization/phase0.py` — a Phase 0 reader: resolve the collection
  name, read bounded documents, expose the documented fields. No Phase 1 namespace
  coupling.
- a Phase 0 command in `cli.py` (alongside `serve|health|profile`), e.g. a `phase0`
  command that lists/inspects/exports without starting Streamlit.
- a minimal Streamlit page only if a browser view is actually needed to verify the
  path; the CLI path should be sufficient to confirm end to end.

Reuse, do not duplicate: `normalize_frame`, `filter_frame`, `load_frame` and the
privacy/`data/` runtime rules already in the repo.

## 6. Restoration strategy

Once Phase 0 works end to end, richer Phase 1 visualization returns **one explicit
feature at a time**, each verified before the next: richer canonical schemas; graph
overlays; provenance views; validation UI; RAG/context views; temporal graph
exploration; DNA/SNA layers; additional dashboards and exports.

The Phase 0 layer should stay deletable — it exists to prove the pipeline, not to
become the permanent architecture.

## 7. Acceptance criteria mapping

| Criterion | Where addressed |
| --- | --- |
| Documented as a thin compatibility layer | §1 |
| Expected MongoDB Phase 0 inputs documented | §2 (verified against code) |
| Minimal useful visualization/export path defined | §3 |
| No Redis/Allas/multimodal/distributed dependency | §4 |

## Open questions (for Tomi)

- Is a browser view needed to verify Phase 0, or is the CLI list/inspect/export path
  sufficient? (Recommendation: CLI first.)
- Should the Phase 0 layer live on the `phase-0` branch only, or land on `main` as an
  explicitly temporary adapter?
- Phase 0 analysis currently emits `source_date` from the feed; is `updated_at` the
  right freshness signal for the Phase 0 view, or should it mirror the `#53`
  freshness warning?
