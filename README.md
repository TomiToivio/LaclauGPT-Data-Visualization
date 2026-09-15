# LaclauGPT Data Visualization

[![tests](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/actions/workflows/tests.yml/badge.svg)](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/actions/workflows/tests.yml)

Researcher-facing dashboards and visualization helpers for the modular LaclauGPT ecosystem. This repository is intentionally independent from the analysis runtime: it reads analysis outputs and presents them without performing data collection or LLM analysis.

The reusable visualization ideas from `TomiToivio/LaclauGPT-Discourse-Analysis` are being extracted here into a clean standalone package: normalized researcher exports, filtering/search, label summaries, Streamlit dashboards, and optional distributed storage adapters. Monolith-specific imports and project-specific research code are deliberately not copied.

## Architecture

The project follows a conventional Python `src/` layout:

```text
src/laclaugpt_visualization/
  app.py       # Streamlit UI
  cli.py       # console launcher
  config.py    # typed environment settings
  data.py      # pure loading/normalization/filtering helpers
  storage.py   # optional MongoDB / Redis / S3 adapters
tests/         # synthetic, data-free unit tests
docs/          # architecture/privacy documentation
```

Implementation code belongs under `src/laclaugpt_visualization/`; tests belong under `tests/`; configuration is typed and environment-driven; optional infrastructure stays behind extras and lazy imports. Keep reusable data transformation logic separate from Streamlit UI code.

## Local-first defaults

A fresh checkout requires no servers. The default profile uses local CSV/JSONL files, SQLite when requested, in-memory caching, and the local filesystem. Put local input files under `data/` (which is gitignored), then run:

```bash
python -m venv .venv
# activate .venv
python -m pip install -e '.[dev]'
laclaugpt-visualize
```

You can also point the dashboard at SQLite by setting `LACLAUGPT_VIS_DATA_BACKEND=sqlite` and `LACLAUGPT_VIS_SQLITE_PATH=data/laclaugpt.sqlite3`.

## Distributed/server profile

Install optional remote adapters with:

```bash
python -m pip install -e '.[remote]'
```

The preferred distributed stack is:

- **MongoDB** for analysis records and dashboard queries;
- **Redis** for optional shared cache/state;
- **S3-compatible object storage** for large artifacts, including CSC Allas.

Copy `.env.example` to `.env` and provide credentials locally. Remote services are opt-in; they must never be required for unit tests or ordinary laptop use.

## Privacy: public repository, private data

**Do not commit research data or private configuration.** The repository ignores `data/`, outputs, CSV/TSV/JSONL/Parquet files, SQLite/DuckDB databases, `.env*` secrets, credentials, keys, certificates, and machine-specific config. Only `.env.example` and sanitized configuration examples belong in Git.

See [docs/PRIVACY_AND_CONFIGURATION.md](docs/PRIVACY_AND_CONFIGURATION.md) before adding new inputs, deployment settings, or integrations.

## Tests and quality

GitHub Actions runs Ruff and Pytest on Python 3.11, 3.12, and 3.13. Locally:

```bash
ruff check .
pytest
```

Tests must use synthetic fixtures only. The green **tests** badge at the top of this README reflects `.github/workflows/tests.yml` on the default branch.

## LaclauGPT modules

Core modules are designed to interoperate through files and stable records rather than importing each other's application internals:

- [LaclauGPT Data Collection](https://github.com/TomiToivio/LaclauGPT-Data-Collection)
- [LaclauGPT Data Analysis](https://github.com/TomiToivio/LaclauGPT-Data-Analysis)
- [LaclauGPT Data Visualization](https://github.com/TomiToivio/LaclauGPT-Data-Visualization)

Visualization should remain a downstream consumer: collection and analysis can run elsewhere (laptop, server, CSC) and publish outputs through CSV/JSONL/SQLite locally or MongoDB/S3 remotely.

## Development rule of thumb

If a feature can be expressed as a pure dataframe transformation, keep it outside Streamlit and test it directly. If it needs credentials or project data, configure it outside Git. If it belongs to collection or analysis, put it in that module instead of growing this repository back into a monolith.
