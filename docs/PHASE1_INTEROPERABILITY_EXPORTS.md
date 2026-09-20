# Phase 1 interoperability exports

Issue #89 restores interoperability/export behavior against the current canonical
Analysis → Visualization contract without changing the preserved Phase 0 exporter.

## Decision

The legacy interoperability module remains available for its explicit DATS/DNA graph
contracts, but it is not used as the canonical-record export path. Canonical records
now have a separate strict nested JSONL export in
`laclaugpt_visualization.canonical_export`.

This is an **adapt** decision:

- preserve the useful legacy DATS/DNA serializers for their own interchange objects;
- add a current-contract canonical JSONL surface beside them;
- do not route canonical records through legacy graph/DATS adapters;
- do not replace or modify Phase 0 JSONL/CSV export.

## Canonical JSONL contract

`canonical_jsonl()` exports one canonical record per line. The export keeps nested
canonical sections intact and preserves `source_url` identity, evidence, provenance
and researcher-review state.

The export is deliberately strict. It refuses records that would require silent
schema coercion, including malformed canonical object/list sections. It also requires
both `schema_version` and `source_url`.

Backend and view-only fields are excluded by construction. MongoDB `_id`, dataframe
helper/search columns and the visualization `raw_record` alias are not part of the
interchange payload.

## Non-goals

This slice does not add CSV/Parquet conversion, mutate source records, infer missing
canonical sections, migrate Phase 0 compatibility records, or alter DATS/DNA graph
exports. Additional formats should be restored independently and only when they can
preserve the canonical semantics without lossy coercion.

## Rollback rule

If a future export format cannot preserve canonical identity/evidence semantics
explicitly, keep that format disabled rather than flattening or guessing.
