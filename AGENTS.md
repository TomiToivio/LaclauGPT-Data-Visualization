# AGENTS.md

## Scope

This repository is the canonical Data Visualization module of LaclauGPT. Keep it strictly downstream of Collection and Analysis. Do not add scrapers, analysis pipelines, model prompts, inference logic or institutional datasets here.

The project-wide data contract is owned by [`TomiToivio/LaclauGPT`](https://github.com/TomiToivio/LaclauGPT/blob/main/docs/CANONICAL_DATA_CONTRACT.md). Read `docs/CANONICAL_DATA_MODEL.md` before changing loaders, persistence, review state or view-model fields.

## AI26 public reference study

AI26 (`Ideological contestation over AI`) is the preferred realistic public example for Visualization because the current modular LaclauGPT system is being developed alongside the public AI26 paper. Read `docs/AI26_REFERENCE_CASE.md` when adding examples, filters, dashboard documentation or synthetic fixtures.

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
