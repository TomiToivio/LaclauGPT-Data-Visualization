# Runtime data layout

All visualization runtime and study-specific material belongs under the repository-local `data/` directory, which remains outside Git.

Use the common structure: `data/logs`, `data/database`, `data/config`, `data/files`, `data/csv`, `data/jsonl`, `data/codebooks`, `data/sources`, `data/downloads`, `data/media`, `data/models/ollama`, `data/models/whisper`, `data/cache`, `data/tmp`, `data/exports`, `data/artifacts`, and `data/runs`.

Visualization outputs belong in `data/exports/` or `data/artifacts/`, not a top-level `outputs/` directory.

When Analysis and Visualization run on the same machine, set `LACLAUGPT_VIS_ANALYSIS_DATA_DIR` to the sibling Analysis module's `data/` directory. Visualization may read canonical analysis outputs directly from there.

For distributed operation, use MongoDB for records, Redis for cache/state, and S3-compatible object storage such as CSC Allas for artifacts. CSV/JSONL transfer remains the manual fallback.
