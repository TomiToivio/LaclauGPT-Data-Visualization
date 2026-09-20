# Phase 0 ontology and discourse graph rendering

Issue #84 decision: **ADAPT**.

Phase 0 graph output may be rendered through the isolated
`phase0_graph.phase0_graph_projection()` adapter. The legacy/current generic canonical graph
projection is not reused for Phase 0 records.

## Why adapt instead of reuse

Phase 0 ontology output is a JSON-LD/Turtle export of Phase 0 discourse analysis. It is not the
canonical Phase 1 relation contract. Reusing `transforms.graph_projection()` would blur the
Analysis/Visualization boundary and could make candidate nodal, floating, and empty signifiers
look like canonical graph claims.

The adapter therefore:

- reads only already-generated Phase 0 JSON-LD under `phase0_ontology`;
- performs no new discourse inference and no co-occurrence-to-relation conversion;
- keeps `source_url` as the source identity on the projection, every node, and every edge;
- retains assertion evidence text emitted by the Phase 0 ontology exporter;
- preserves the Phase 0 `validated` flag only as source metadata while still labeling the
  rendered graph itself `candidate/provisional`;
- labels nodal, floating, and empty signifier nodes explicitly as candidates;
- synthesizes display-only endpoint nodes for assertion URIs that the Phase 0 exporter references
  but does not emit as separate resources;
- enforces node/edge bounds and reports truncation;
- never calls the canonical Phase 1 graph transform.

## Epistemic label

Every Phase 0 projection carries:

`graph_semantics = "phase0-candidate/provisional"`

and an interpretation warning stating that graph layout, degree, relation presence, and ontology
classes do not establish theoretical validity or human validation.

## Default enablement

This adapter is deliberately not wired into the default canonical graph UI by this issue.
Integration can enable it only through an explicit Phase 0 path after the bounded canonical graph
prerequisite is proven. Removing that future integration leaves Phase 0 list/inspect/export
behavior unchanged.

## Rollback

Delete the isolated adapter, its tests, and this decision note. No canonical transform, Phase 0
storage shape, or Phase 0 list/inspect/export behavior depends on it.
