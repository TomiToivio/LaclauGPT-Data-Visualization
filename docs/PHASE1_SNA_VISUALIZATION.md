# Phase 1 SNA visualization

Issue #95 restores Social Network Analysis visualization as an **isolated downstream capability**.

## Decision: adapt, do not infer

The current Analysis repository exposes provenance-rich `NetworkNode` and `NetworkEdge`
structures plus deterministic descriptive graph measures, but that Analysis layer remains
experimental and is not part of the default pipeline. Visualization therefore adapts an
explicit `ProductKind.NETWORK` product when one is supplied. It does not create an SNA
network from ordinary canonical records, co-mentions, shared topics, shared ideology, or
layout proximity.

If no explicit upstream NETWORK product is available, the SNA capability is unavailable.
That is the rollback-safe state required by issue #95.

## Accepted upstream shape

The adapter accepts a mapping with list-valued `nodes` and `edges`.

Nodes use the Analysis vocabulary where available:

- `node_id`, `node_type`, `label`, optional `metadata`;
- `id` / `type` are accepted as transport aliases.

Edges preserve:

- `source`, `target`, `relation_type`;
- `observed`, `weight`, `timestamp`, `platform`, `collection_id`;
- `source_url`, `evidence_ids`, optional `metadata`.

Optional upstream `measures` may contain `degree`, `in_degree`, `out_degree`,
`betweenness`, `pagerank`, `clustering`, and `k_core`. Visualization displays
these values but never computes missing measures.

## Provenance and identity

Edge `source_url` and evidence identifiers are preserved into the shared
`laclaugpt.graph.v1` envelope. Product-level `EvidenceRef` objects remain available for
drill-down. No backend ID replaces canonical source identity.

## Bounding

The renderer applies explicit node/edge limits. When upstream degree is available it may
be used only to prioritize which already-existing nodes fit inside the display bound.
Without upstream degree, input order is retained. Bounding never manufactures an edge.

## Interpretation caveat

Degree, centrality, PageRank, clustering, component membership and layout are descriptive
structural measures. They do not by themselves establish influence, power, hegemony,
ideology, coordination, brokerage, or theoretical significance.

## Phase boundary

This capability is read-only Visualization. SNA extraction, graph construction, metric
calculation, community detection and theoretical interpretation remain Analysis concerns.
The preserved Phase 0 list/inspect/export path is untouched.
