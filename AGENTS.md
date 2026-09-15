# AGENTS.md

## Scope

This repository is the canonical Data Visualization module of LaclauGPT. Keep it strictly downstream of Collection and Analysis. Do not add scrapers, analysis pipelines, model prompts, inference logic or institutional datasets here.

## Mandatory architecture rules

1. UI code renders or edits view/review state. It never performs discourse analysis.
2. Canonical Collection/Analysis records are the primary input contract. Do not import sibling implementation internals.
3. Legacy EP24/AI26 shapes are boundary-adapter concerns only. Do not leak historical column names into core models.
4. Keep data loaders, transforms, review persistence and Streamlit page orchestration separate.
5. Never connect to MongoDB, Redis, S3 or any network service at import time.
6. Preserve local-first operation with files/SQLite/local filesystem only.
7. Use typed review state and preserve `source_url`, schema version, provenance, uncertainty and review semantics.
8. Visualization may request reprocessing/reruns but must not implement the analysis pipeline itself.
9. Add synthetic tests for substantial loaders, adapters, transformations, review behavior and view-model changes.
10. Keep public APIs small and avoid giant dashboard modules or mutable process-global research state.

## Epistemic/theoretical boundary

Laclau/Mouffe/Palonen concepts require human interpretation. Frequency, centrality, graph degree, layout, model confidence or co-occurrence do not automatically establish hegemony, nodal status, empty/floating signification, equivalence, antagonism or political frontier validity. Present such outputs as descriptive observations or provisional candidates unless human review has validated the interpretation.

## Mandatory runtime data boundary

All runtime and study-specific material belongs below `data/`, and the whole `data/` tree stays outside Git. Follow `docs/RUNTIME_DATA.md`.

Logs, databases, local configuration, CSV/JSONL files, downloaded files, media, caches, exports, artifacts, temporary files and researcher review state all belong under `data/`. Visualization output defaults to `data/exports/`; local review state defaults to `data/database/reviews.sqlite3`.

When Analysis and Visualization run on the same host, use `analysis_data_dir` to read canonical output from the sibling Analysis `data/` tree. In distributed mode use MongoDB for records, Redis for cache/coordination/pub-sub where useful, and S3-compatible storage for referenced artifacts. CSV/JSONL transfer remains the manual fallback.

## Privacy

This is a public repository. Never commit row-level research data, transcripts, OCR, frames/media, researcher notes, review databases, generated exports, caches, `.env`, `.streamlit/secrets.toml`, credentials, private endpoints, institutional usernames/project IDs, machine-specific absolute paths or private target/source lists.

Only tiny explicitly synthetic fixtures belong in tests/examples. Run `python scripts/check_public_tree.py` before merging.

## Quality gate

Before merging run:

```bash
python scripts/check_public_tree.py
ruff check .
pytest
```

Keep GitHub Actions green across supported Python versions.
