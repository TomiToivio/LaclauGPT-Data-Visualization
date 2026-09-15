# LaclauGPT Data Visualization

[![tests](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/actions/workflows/tests.yml/badge.svg)](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/actions/workflows/tests.yml)

**LaclauGPT-Data-Visualization is the canonical visualization implementation repository** in the modular LaclauGPT architecture. It consumes canonical Collection/Analysis records and provides one researcher-facing application with Monitor, Researcher Review, and Explore modes. It does not perform collection or discourse inference itself.

## Unified application

- **Monitor**: near-real-time corpus status, analyzed/awaiting-analysis counts, latest source/analysis timestamps, formations, signifiers, actors and descriptive activity summaries.
- **Researcher Review**: one-record close reading with transcript, OCR, multimodal/frame evidence, human-readable summary, structured analysis fields, provenance, uncertainty, typed corrections, notes and rerun/reprocess requests.
- **Explore**: shared filters, timelines, formation/topic/entity distributions, relation tables and graph-projection inputs.

Counts, model confidence, graph degree and layout are descriptive aids. They do not by themselves establish hegemony, nodal status, empty/floating signification, antagonism or theoretical validity.

## Canonical data boundary

```text
LaclauGPT-Data-Collection
        ↓ canonical records
LaclauGPT-Data-Analysis
        ↓ canonical analysis results
LaclauGPT-Data-Visualization
```

Canonical nested JSON/JSONL is primary. Stable `source_url`, schema version, provenance, review status, uncertainty/abstention and multimodal references are preserved into the visualization view model. Historical EP24 flat exports are supported only through `legacy_ep24.py`; legacy column names never become the core schema.

## Runtime data boundary

All runtime and study-specific material lives under `data/`, which is entirely excluded from Git. Common locations include `data/logs/`, `data/database/`, `data/config/`, `data/files/`, `data/csv/`, `data/jsonl/`, `data/cache/`, `data/exports/`, `data/artifacts/` and `data/tmp/`. Researcher reviews default to `data/database/reviews.sqlite3`.

Never commit row-level EP24/AI26 data, transcripts, OCR, media, researcher notes, review databases, caches, filtered exports, `.env`, Streamlit secrets, credential-bearing URIs, private hostnames or machine-specific paths.

## Local same-machine pipeline

```bash
export LACLAUGPT_VIS_ANALYSIS_DATA_DIR=../LaclauGPT-Data-Analysis/data
python -m pip install -e '.[dev]'
laclaugpt-visualize
```

Local operation requires no services: CSV/JSON/JSONL/SQLite plus local filesystem and the SQLite review store are sufficient.

## Distributed pipeline

Install remote adapters with:

```bash
python -m pip install -e '.[remote]'
```

MongoDB may carry canonical records, Redis may provide cache/pub-sub/state, and S3-compatible storage such as CSC Allas may carry referenced artifacts. All are optional and lazy. CSV/JSONL remains the manual cross-machine fallback.

## Architecture

```text
src/laclaugpt_visualization/
  app.py              # page orchestration only
  canonical.py        # public canonical record boundary
  data.py             # loaders, normalization, filters
  legacy_ep24.py      # bounded legacy compatibility
  transforms.py       # pure monitor/explore view models
  review/             # typed review model + SQLite/Mongo stores
  storage.py          # optional remote adapters
  config.py
```

See `docs/UNIFIED_DASHBOARD.md` and `docs/MIGRATION_REPORT.md` for feature mapping from the public visualization subtree, AI26 live dashboard and EP24 researcher dashboard.

## Privacy and quality

Normal CI is fully synthetic/offline and runs the public-tree privacy guard, Ruff and pytest on Python 3.11, 3.12 and 3.13.

```bash
python scripts/check_public_tree.py
ruff check .
pytest
```

See `AGENTS.md`, `docs/PRIVACY_AND_CONFIGURATION.md`, and `docs/RUNTIME_DATA.md`.
