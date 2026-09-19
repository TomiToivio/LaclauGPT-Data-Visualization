# Phase-1 optional visualization libraries

Status: **backlog implementation scaffold, not activated in Phase 0**.

Issue #99 adds reusable interchange adapters and isolated research prototypes without touching the current Streamlit/Plotly defaults.

## Added surfaces

- Python serializers:
  - `to_cytoscape()`
  - `to_graphology()`
  - `to_graphml()`
  - `to_tidy_tables()`
- optional browser prototypes:
  - Cytoscape.js small actor-concept graph
  - Sigma.js + Graphology larger synthetic scale test
- optional R reproducibility scripts:
  - timeline figure with ggplot2
  - network figure with igraph/ggraph

The serializers accept already-derived node/edge projections and retain provenance fields such as `source_urls` and `evidence_refs`. They do **not** calculate centrality, communities, discourse classifications or theoretical interpretations.

## Deferred candidates

Observable Plot, Arquero, DuckDB-Wasm, Altair, quanteda.textplots, rDNA and a locked `renv` environment remain evaluation targets for Phase 1. They are intentionally not added to Phase-0 dependency manifests.

## Scientific boundary

Every graph output is descriptive. Degree is not a nodal point, layout proximity is not equivalence, cluster membership is not ideology, and frequency is not hegemony.

## Activation

Nothing in this scaffold is imported by the default dashboard entrypoint. Phase 1 can promote individual components after benchmark/researcher review without changing the canonical data contract.
