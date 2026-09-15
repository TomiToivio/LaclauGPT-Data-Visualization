# LaclauGPT Data Visualization

[![tests](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/actions/workflows/tests.yml/badge.svg)](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/actions/workflows/tests.yml)

Researcher-facing dashboards and visualization helpers for the modular LaclauGPT ecosystem. Visualization consumes analysis outputs without performing collection or analysis itself.

## Runtime data boundary

All runtime and study-specific material lives under `data/`, which is entirely excluded from Git. See `docs/RUNTIME_DATA.md`.

Common locations include `data/logs/`, `data/database/`, `data/config/`, `data/files/`, `data/csv/`, `data/jsonl/`, `data/cache/`, `data/exports/`, and `data/artifacts/`. The default SQLite file is `data/database/visualization.sqlite3`, and generated visualization output goes to `data/exports/`.

Do not create a top-level `outputs/`, `logs/`, `database/`, or other runtime directory.

## Local same-machine pipeline

If Analysis is checked out beside Visualization, configure:

```bash
export LACLAUGPT_VIS_ANALYSIS_DATA_DIR=../LaclauGPT-Data-Analysis/data
```

Visualization may then read canonical Analysis output directly from the sibling module's private `data/` tree.

For SQLite mode:

```bash
export LACLAUGPT_VIS_DATA_BACKEND=sqlite
export LACLAUGPT_VIS_SQLITE_PATH=data/database/visualization.sqlite3
```

## Distributed pipeline

Install remote adapters with:

```bash
python -m pip install -e '.[remote]'
```

The preferred distributed stack is MongoDB for records, Redis for shared cache/state, and S3-compatible object storage such as CSC Allas for large artifacts. CSV/JSONL file transfer remains the explicit manual fallback.

## Architecture

```text
src/laclaugpt_visualization/
  app.py
  cli.py
  config.py
  data.py
  storage.py
tests/
docs/
```

Keep pure data transformations separate from Streamlit UI code. Optional infrastructure stays lazy and behind extras. Interoperate through stable files/records/APIs rather than importing sibling implementation internals.

## Installation

```bash
python -m venv .venv
# activate .venv
python -m pip install -e '.[dev]'
laclaugpt-visualize
```

## Privacy and quality

This is public code with private runtime data. Tests use synthetic fixtures only; operational data/configuration belongs under `data/` or external deployment systems.

Run:

```bash
ruff check .
pytest
```

See `AGENTS.md`, `docs/PRIVACY_AND_CONFIGURATION.md`, and `docs/RUNTIME_DATA.md`.
