# AGENTS.md

## Scope

This repository is the **Data Visualization** module of LaclauGPT. Keep it downstream of collection, storage, and analysis. Do not add scrapers, LLM pipelines, model prompts, project-specific codebooks, or institutional datasets here.

## Python architecture

- Put importable implementation code under `src/laclaugpt_visualization/`.
- Keep dataframe transformations and adapters independent of Streamlit whenever practical.
- Put tests under `tests/` and use synthetic fixtures only.
- Add dependencies to `pyproject.toml`; keep optional infrastructure behind extras and lazy imports.
- Prefer typed configuration and small modules over global mutable settings.
- Preserve local-first operation. The package must remain useful without MongoDB, Redis, S3, CSC, or network access.
- Interoperate with other LaclauGPT modules through stable files/records/APIs, not cross-repository imports of application internals.

## Privacy

This is a public repository. Never commit real research data, row-level samples, transcripts, media, credentials, private endpoints, CSC project paths, bucket secrets, cookies, tokens, `.env` files, or machine-specific configuration. Follow `docs/PRIVACY_AND_CONFIGURATION.md` and verify `git status` before pushing.

## Backends

Default/small installation:
- CSV/JSONL/Parquet input when explicitly provided
- SQLite for structured local data
- local filesystem for artifacts
- process memory for cache

Optional distributed deployment:
- MongoDB for records
- Redis for cache/state
- S3-compatible object storage (including CSC Allas) for large artifacts

Remote services must be configured only through environment variables or external secret management.

## Quality gate

Before merging changes, run:

```bash
ruff check .
pytest
```

GitHub Actions must remain green on the supported Python versions.
