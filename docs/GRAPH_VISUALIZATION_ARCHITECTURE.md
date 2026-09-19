# Backend-neutral graph visualization architecture

Status: Phase-0 implementation scaffold for issue #101. Existing dashboards remain unchanged by default.

## Contract

Visualization uses `laclaugpt.graph.v1`, represented by `GraphQuery` and `GraphEnvelope` in
`src/laclaugpt_visualization/graph_api.py`. The browser/UI does not know whether a graph came
from local CSV/SQLite-derived exports, MongoDB, or optional ArangoDB traversal.

Every response contains bounded nodes and typed edges plus optional continuation,
metadata and provenance. Nodes and edges can carry `provenance_refs` so a researcher can move
from an analytical relation to source evidence without creating a second evidence store.

## Layers and phase safety

The shared layer vocabulary is:

- `source` and `provenance`: documents/posts/media, accounts/organizations, collection and derivation paths.
- `laclau`: precomputed signifiers, nodal-point candidates, equivalence/difference relations, formations,
  actors/positions, themes and evidence links.
- `dna`: actor-concept/statement networks, stance/agreement/conflict and temporal coalitions.
- `sna`: interaction networks, weighted/directed edges, communities, metrics and temporal snapshots.

DNA and SNA are gated by `layer_enabled(..., phase=2)`. This repository does not compute any of
those classifications; it only renders upstream analytical objects.

## Backends

`LocalGraphBackend` wraps a bounded local loader suitable for CSV/SQLite exports.
`MongoGraphBackend` wraps the existing Mongo query layer without leaking Mongo identifiers into the UI.
`ArangoGraphBackend` is optional and dependency-free at import time; a provider with bounded
`traverse()` and `describe()` methods is injected by deployment code.

The same synthetic fixture is required to normalize to the same contract across all three adapters.

## Rendering

Keep renderer choice separate from the contract. Cytoscape.js is the preferred interactive renderer for
typed research graphs because compound styling, directed/weighted edges, selection and neighborhood
interaction map well to the requirements. Sigma/Graphology remains useful for very large sparse SNA
views. Plotly/D3-style custom views can remain for specialized temporal or explanatory views.

Large graphs must use bounded queries, progressive neighborhood expansion, continuation tokens,
aggregation or server-side clustering. Never render the entire research database in one browser graph.

## Research controls

A graph explorer built on this contract should expose node/edge type, study/collection, time,
arena/platform/language/region, search/entity focus, ego/k-hop expansion, analytical-layer toggles,
direction/weight controls, time-slice comparison, evidence/provenance inspection, legend/semantics,
and selected-subgraph export.

`jsonld_subgraph()` provides a portable JSON-LD-shaped export for a selected bounded subgraph.
Turtle materialization may remain Analysis-owned where richer ontology/prefix handling is required.

## Semantics

Visualization does not infer discourse theory from layout or graph statistics. Degree, centrality,
communities and co-occurrence remain descriptive unless upstream analysis and human review provide
the stronger semantic claim.
