# Optional R visualization workflows

These scripts are reproducible research-figure companions to the normal Python/browser dashboard. They are optional and are not required by core CI.

Inputs should come from portable LaclauGPT exports such as CSV, GraphML, JSON or Parquet/Arrow. Analytical inference belongs upstream in Data Analysis; these scripts visualize explicit outputs and preserve semantics in figure captions/metadata.

Examples:

```bash
Rscript scripts/r/dna_network_plot.R nodes.csv edges.csv dna-network.pdf
Rscript scripts/r/tabular_figure.R timeline.csv day count timeline.pdf
```

Recommended packages:

- `ggplot2`
- `igraph`
- `arrow` for Parquet
- `quanteda` for visualization of already-prepared text/statistical results where appropriate
- `stm` for figures from saved/exported STM results
- `rDNA`/DNA-compatible tables for discourse-network figures

Do not treat layout position, centrality, community membership, topic prevalence or visual prominence as a Laclauian construct without an explicit theoretical and methodological argument.
