<!-- PHASE-BRANCH-POLICY:v3 -->

## Mandatory phase-branch policy

LaclauGPT keeps persistent phase branches: `phase-0`, `phase-1`, `phase-2`, `phase-3`, and `phase-4`.

**Current active/stable phase: Phase 2.** All Phase 2 development, fixes, issue work, and pull requests target `main` directly. The `phase-2` ref is a passive compatibility/mirror branch and MUST represent the same validated tree as `main`; agents must not use it as the source or target branch for Phase 2 work. The `phase-1` branch is the preserved Phase 1 baseline, and `phase-0` remains the preserved Phase 0 baseline.

Before making any issue-driven change, an agent MUST determine the issue's intended phase from explicit issue text, title, labels, milestone, linked plan, or repository documentation. Then:

1. Phase 2 work starts from `main` and targets `main` directly. Short-lived issue branches, when useful, are created from `main` and PR back to `main`.
2. Do not create new Phase 2 work from `phase-2`, and do not target Phase 2 PRs at `phase-2`.
3. After validated Phase 2 changes land on `main`, keep the passive `phase-2` mirror synchronized to the same commit/tree.
4. Phase 3 and Phase 4 work stays on the matching persistent `phase-N` branch (or a short-lived branch created from it) and must not land on `main` while Phase 2 is current.
5. Phase 1 maintenance targets `phase-1`; Phase 0 maintenance targets `phase-0`. Neither maintenance line moves `main` backward.
6. If an issue has no phase information, treat it as belonging to the current phase unless the task or roadmap clearly says otherwise. Currently that means Phase 2 on `main`.
7. Do not silently move work between phases. If implementation reveals that an issue belongs to another phase, update/document the issue or report the mismatch before merging.
8. Preserve `TOMI-LOCKED`, privacy, public/private, runtime-data, scientific-method, and module-boundary rules on every branch.

See `docs/PHASE_BRANCHING.md` for the repository-wide workflow.

# AGENTS.md

## Broad agent role

Agents in this repository may act as **research-visualization engineers, visual analytics specialists, research assistants, dashboard operators, review-workflow maintainers and data-quality auditors**. They should understand the research questions well enough to build useful, accurate views, inspect canonical records, diagnose misleading charts or broken adapters, support human review, and document uncertainty and provenance.

This broad role does not move analysis into the UI. Agents may explain or contextualize existing analytical outputs, but they must not create new theoretical classifications, scrape new sources, or silently reinterpret canonical records inside Visualization.

Before guessing study-specific semantics, inspect repository documentation and public reference configuration. For AI26, read `docs/AI26_REFERENCE_CASE.md`, then the public canonical data/model docs and any explicitly referenced codebook/configuration. Canonical repository files outrank model memory; legacy dashboards are archaeology/compatibility references only.

## Scope

This repository is the canonical Data Visualization module of LaclauGPT. Keep it strictly downstream of Collection and Analysis. Do not add scrapers, analysis pipelines, model prompts, inference logic or institutional datasets here.

The project-wide data contract is owned by [`TomiToivio/LaclauGPT`](https://github.com/TomiToivio/LaclauGPT/blob/main/docs/CANONICAL_DATA_CONTRACT.md). Read `docs/CANONICAL_DATA_MODEL.md` before changing loaders, persistence, review state or view-model fields.


## AI26 Phase 2 scope lock

**This repository's `main` branch is now exclusively the AI26 Phase 2 implementation.**

- AI26 is the only active/default study in this repository. New code, configuration, tests, examples, documentation, commands and agent work MUST assume AI26 unless Tomi explicitly says otherwise.
- EP24, Hungary26 and Brazil26 are out of scope here. They will live in separate project repositories. Do not add new EP24/Hungary26/Brazil26 pipelines, codebooks, launchers, dashboards, adapters, deployment documentation or project-specific defaults here.
- Historical compatibility code may remain temporarily when removing it would create unnecessary risk, but agents must treat it as dormant legacy. Do not extend, polish, modernize or use it as an architectural target.
- The human-readable publication/researcher-facing versions belong in the legacy EP24 repositories or other project-specific repositories. These three AI26 repositories do **not** need to optimize for human readability right now.
- Prefer machine-readable canonical records, provenance, evidence, reproducible Phase 2 processing and operational correctness over prose reports, human-readable summaries, researcher workbenches, exhibition views or legacy dashboards.
- Do not spend issue scope on making outputs friendlier to humans unless Tomi explicitly requests it. Human-in-the-loop scientific validation remains required; this rule is about software/output presentation, not removing human research responsibility.
- Phase 2 work goes directly to `main` under the repository's current branch policy. Phase 0/1 branches remain historical baselines and are not defaults for new work.

## Research visualization practice

Agents should:

- choose visual encodings that match the measurement scale and uncertainty of the underlying data;
- preserve provenance, abstention, multi-label overlap and human-review state;
- make descriptive vs interpretive outputs visually distinguishable;
- inspect data completeness, duplicates, missing timestamps/locations and backend inconsistencies before blaming the chart;
- avoid implying causality, hegemony, ideological identity or theoretical validity from frequency/centrality/layout alone;
- support maps, timelines, networks, comparisons and reports when the canonical data actually supports them;
- prioritize operationally useful AI26 Phase 2 views and reproducible machine-readable outputs over presentation polish;
- leave legacy dashboards dormant; do not extend or polish them unless Tomi explicitly requests migration/maintenance.

## AI26 active study

AI26 (`Ideological contestation over AI`) is the active and default study for Visualization. The current `main` implementation is AI26 Phase 2. Read `docs/AI26_REFERENCE_CASE.md` when adding examples, filters, dashboard documentation or synthetic fixtures.

Use the three AI26 arenas (`elites`, `grassroots`, `parliamentary`) and the public AI26 codebook as realistic examples, but never hard-code them into core models or generic UI contracts. Arena is sampling provenance, not ideology.

The six current computational formation labels (`accelerationism`, `doomerism`, `left-wing accelerationism`, `ai safety`, `ai critical`, `anti-ai`) are provisional aggregation anchors. Visualizations must preserve multi-label overlap, uncertainty, abstention and human review instead of presenting them as exhaustive or permanent actor identities.

Current terms such as safety, pacing, competition, innovation, China, control, liability, independent evaluation, regulation, labour, ownership, surveillance and data centres are useful public reference filters. They remain candidate signifiers/context terms. A chart must not turn frequency, centrality or co-occurrence into a theoretical conclusion.

Public-safe AI26 dashboard semantics and synthetic fixtures may be committed. Real AI26 records, private watch lists, researcher annotations, credentials/endpoints and generated private reports remain outside Git.

## Mandatory architecture rules

1. UI code renders or edits view/review state. It never performs discourse analysis.
2. Canonical Collection/Analysis records are the primary input contract. Do not import sibling implementation internals.
3. **Reconstruct the canonical nested record before applying visualization semantics.** CSV/Pandas, SQLite, MongoDB, JSON/JSONL and Parquet are storage/transport adapters, not alternative schemas.
4. `source_url` (including stable URI-like identifiers) is the canonical source identity for selections, review state and exports. `document_id`, `video_id`, `new_id`, Mongo `_id`, SQLite PKs and row indexes are aliases/implementation details only.
5. Do not add dashboard-specific persistent fields when the information belongs in the canonical `source`, `content`, `evidence`, `analysis`, `provenance` or `review` sections. View-model columns may reshape canonical data for display but must not redefine its meaning.
6. Legacy EP24/AI26 shapes are boundary-adapter concerns only. Do not leak historical column names into core models.
7. Keep data loaders, canonical reconstruction, transforms, review persistence and Streamlit page orchestration separate.
8. Never connect to MongoDB, Redis, S3 or any network service at import time.
9. Preserve local-first operation with files/SQLite/local filesystem only.
10. Use typed review state and preserve `source_url`, schema version, provenance, uncertainty, abstention and review semantics.
11. Visualization may request reprocessing/reruns but must not implement the analysis pipeline itself.
12. Add synthetic tests for substantial loaders, adapters, transformations, review behavior and view-model changes. Cross-backend tests must verify semantic equivalence without live services.
13. Keep public APIs small and avoid giant dashboard modules or mutable process-global research state.

## Serialization rules

- JSON/JSONL is the reference nested representation.
- Flat CSV/SQLite representations must use deterministic JSON for nested objects/lists and must reconstruct them before visualization.
- Do not parse or emit Python `repr` as a persistent interchange format.
- Preserve `schema_version` and `source_url` across every adapter.
- Normalize view-layer timestamps to timezone-aware UTC while retaining the original canonical record/provenance.
- Missing optional multimodal fields remain absent/empty; never invent transcript, OCR, frame or media values for text-only records.
- Backend-specific IDs must never enter the canonical identity path.

## Epistemic/theoretical boundary

Laclau/Mouffe/Palonen concepts require human interpretation. Frequency, centrality, graph degree, layout, model confidence or co-occurrence do not automatically establish hegemony, nodal status, empty/floating signification, equivalence, antagonism or political frontier validity. Present such outputs as descriptive observations or provisional candidates unless human review has validated the interpretation.

## Deployment and operations

Visualization may run locally or as a Linux web service. Distributed mode may read MongoDB canonical records, use Redis for project-scoped cache/coordination/settings, and resolve large artifacts from S3-compatible storage such as CSC Allas. Agents may inspect service health, loaders, caches and review workflows, but must not invent private endpoints/domains/CSC values or mutate shared infrastructure without explicit task authorization.

## Mandatory runtime data boundary

All runtime and operational study material belongs below `data/`, and the whole `data/` tree stays outside Git. Follow `docs/RUNTIME_DATA.md`.

Logs, databases, local configuration, CSV/JSONL files, downloaded files, media, caches, exports, artifacts, temporary files and researcher review state all belong under `data/`. Visualization output defaults to `data/exports/`; local review state defaults to `data/database/reviews.sqlite3`.

When Analysis and Visualization run on the same host, use `analysis_data_dir` to read canonical output from the sibling Analysis `data/` tree. In distributed mode use MongoDB for records, Redis for cache/coordination/pub-sub where useful, and S3-compatible storage for referenced artifacts. CSV/JSONL transfer remains the manual fallback.

## Privacy

This is a public repository. Never commit row-level research data, transcripts, OCR, frames/media, researcher notes, review databases, generated exports, caches, `.env`, `.streamlit/secrets.toml`, credentials, private endpoints, institutional usernames/project IDs, machine-specific absolute paths or private target/source lists.

Private repositories may be inspected when authorized to understand reusable behavior and publication-safe study methodology. Public-safe AI26 conceptual/configuration examples may be adapted into this repository; never copy private data, credentials, unpublished target lists, researcher notes or operational deployment state.

Only tiny explicitly synthetic fixtures belong in tests/examples. Run `python scripts/check_public_tree.py` before merging.

## Quality gate

Before merging run:

```bash
python scripts/check_public_tree.py
ruff check .
pytest
```

Keep GitHub Actions green across supported Python versions.

## TOMI-LOCKED

Anything marked `TOMI-LOCKED` is a human-controlled invariant.

Agents MUST NOT modify, refactor, rename, migrate, remove, reinterpret, or change the semantics of a TOMI-LOCKED element.

This includes indirect changes whose effect would alter a locked interface, data format, workflow, behavior, assumption, prompt, schema, configuration, or documented contract.

When an agent encounters `TOMI-LOCKED`:

1. Preserve the marked element exactly unless Tomi's current instruction explicitly authorizes changing that specific locked element.
2. Do not bypass the lock through dependent code, schemas, serializers, migrations, tests, prompts, documentation, interfaces, configuration, or compatibility layers.
3. Do not remove the `TOMI-LOCKED` marker during cleanup, refactoring, migration, modernization, or documentation work.
4. Broad instructions such as "refactor", "modernize", "fix everything", "make CI green", "update the pipeline", or similar do NOT override a lock.
5. If a requested task conflicts with a locked element, preserve the lock, complete any non-conflicting work that is safe to do, and clearly report the conflict.
6. If Tomi explicitly authorizes a change to a specific locked element, that element may be changed, but the `TOMI-LOCKED` marker remains unless Tomi explicitly asks to remove the lock itself.

Only explicit authorization from Tomi for the specific locked element overrides the lock.

Marker examples:

```python
# TOMI-LOCKED
# Do not modify without explicit approval from Tomi.
```

```markdown
<!-- TOMI-LOCKED -->
```

```yaml
# TOMI-LOCKED
```

The marker is intentionally grep-friendly:

```bash
grep -R "TOMI-LOCKED" .
```

