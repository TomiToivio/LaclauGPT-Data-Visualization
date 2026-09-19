# Phase-1 R reproducibility layer

This directory is optional and independent from the Python dashboard. It reads portable exports and writes publication/QA artifacts under the ignored `data/artifacts/` or `data/exports/` tree.

Suggested packages:

`ggplot2`, `igraph`, `tidygraph`, `ggraph`, `patchwork`, optional `plotly`, `quanteda.textplots`, `rDNA`, and `renv`.

Bootstrap locally with `renv::init()` when Phase 1 resumes. Do not activate R in Phase 0 CI/runtime.

Examples:

```bash
Rscript scripts/R/timeline_figures.R data/exports/timeline.csv data/artifacts/timeline.png
Rscript scripts/R/network_figures.R data/exports/nodes.csv data/exports/edges.csv data/artifacts/network.png
```

The scripts only render descriptive exports. They do not infer nodal points, hegemony, equivalence, ideology or antagonistic frontiers.
