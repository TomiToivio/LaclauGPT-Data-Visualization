# Migration from LaclauGPT-Discourse-Analysis

The former monolithic repository contains a larger `laclaugpt/visualization/` package. This standalone repository extracts the parts that remain useful after the project is split into modules.

## Extracted/reimplemented here

- `data.py`: portable loading, normalization, researcher search/filtering, and label summaries are now in `src/laclaugpt_visualization/data.py` and no longer depend on the monolith's internal configuration or schema classes.
- `runtime.py`: the Slurm/CSC Roihu interactive-dashboard guard is ported directly in adapted form and covered by tests.
- `app.py`, `dashboard.py`, `live_dashboard.py`, `unified_dashboard.py`: their researcher-facing Streamlit concepts are consolidated into the standalone `app.py` instead of preserving several overlapping entry points.
- `launcher.py`: replaced by the package console script `laclaugpt-visualize` and `cli.py`.
- storage-facing behavior is moved behind `storage.py`, with local files/SQLite by default and optional MongoDB, Redis, and S3 adapters.

## Not copied verbatim

- `graph.py` depends on the monolith's `laclaugpt.graph` implementation and interchange model. Graph projection belongs either in Data Analysis or behind a stable shared interchange API before it is reintroduced here.
- `review.py` contains analysis/review workflow responsibilities that should not silently make the visualization module a second analysis backend. A future review UI should write through an explicit Analysis/Storage contract.
- monolith-specific project/arena configuration imports are intentionally removed. Cross-repository imports of application internals are not allowed.

## Rule for future extraction

When useful visualization functionality still exists only in the monolith, port the smallest reusable behavior into this package, remove project-specific assumptions, give it a stable input contract, and add synthetic tests. Do not copy old code merely to preserve file-for-file similarity.
