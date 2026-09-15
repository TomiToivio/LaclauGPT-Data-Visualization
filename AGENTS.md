# AGENTS.md

## Scope

This repository is the Data Visualization module of LaclauGPT. Keep it downstream of collection and analysis. Do not add scrapers, analysis pipelines, model prompts, or institutional datasets here.

## Mandatory runtime data boundary

All runtime and study-specific material belongs below `data/`, and the whole `data/` tree stays outside Git. Follow `docs/RUNTIME_DATA.md`.

Logs, databases, local configuration, CSV/JSONL files, source lists, codebooks, downloaded files, media, caches, exports, artifacts, temporary files and local model material all belong under `data/`. Visualization output defaults to `data/exports/`.

Do not create top-level runtime roots such as `outputs/`, `logs/`, `database/`, `downloads/` or model-cache directories. Use `Settings.data_dir`, `Settings.data_path()` and `Settings.ensure_local_directories()`.

When Analysis and Visualization run on the same host, use `analysis_data_dir` to read canonical analysis output directly from the sibling Analysis module's `data/` tree. In distributed mode use MongoDB, Redis and S3-compatible storage such as CSC Allas. CSV/JSONL transfer is the manual fallback.

## Python architecture

- Put importable code under `src/laclaugpt_visualization/`.
- Keep dataframe transformations and adapters independent of Streamlit where practical.
- Use synthetic fixtures only in tests.
- Keep optional infrastructure behind extras and lazy imports.
- Preserve local-first operation without remote services.
- Interoperate through stable files/records/APIs rather than sibling implementation imports.

## Privacy

This is a public repository. Runtime research material and operational configuration stay outside Git under `data/` or external deployment systems. Follow `docs/PRIVACY_AND_CONFIGURATION.md`.

## Backends

Local mode uses files/SQLite/local filesystem. Distributed mode may use MongoDB for records, Redis for cache/state, and S3-compatible object storage including CSC Allas.

## Quality gate

Before merging run `ruff check .` and `pytest`, and keep GitHub Actions green.
