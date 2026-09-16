# Legacy dashboard audit for issue #18

This audit records what is safe to preserve from historical dashboards and what must not be copied into the maintained visualization package.

## EP24 researcher dashboard

Reference: `TomiToivio/ep2024_postprocess/dashboard/dashboard.py`.

### Preserve as behavior

- dense researcher-facing table and record drill-down;
- transcript, translation, OCR, sampled frame/frame-analysis and source metadata inspection;
- historical themes, entities, sentiments, topic-model and Formula-of-Populism fields when they exist;
- researcher review flags and notes as a workflow concept;
- filtering by source/country/date and selection by stable record identity.

### Bugs and architecture risks found

- A MongoDB connection URI with credentials is hard-coded in source. It must never be copied. Any still-valid exposed credential should be considered compromised and rotated outside this repository.
- Database access is created at module import time, preventing safe offline/read-only use.
- UI, storage, transformations and review persistence are interleaved in one large Streamlit module.
- `global df` / `global selected_index` state makes rerun behavior hard to reason about and test.
- Local `researcher_notes.json` is assumed to exist, and review state is split across local JSON and MongoDB.
- Full MongoDB documents and researcher notes are printed to stdout, which may disclose restricted material in logs.
- Historical columns are directly hard-coded into UI layout and can raise errors for partial/older exports.
- Several list-like fields rely on inconsistent delimiters and ad-hoc string parsing.
- Date handling is duplicated rather than normalized at the adapter boundary.
- Plotting helpers are duplicated across historical dashboard implementations.
- Authentication/privacy assumptions are entangled with the application rather than deployment configuration.

The maintained implementation therefore preserves the researcher workflow through `legacy_ep24.py`, normalized view models and the private review store, not by copying the old monolith.

## VASAMA/OSINT dashboard

Reference: `TomiToivio/vasama-osint`, branch `OSINT`, `osint_dashboard.py`.

### Preserve as general visualization concepts

- one/many-event maps;
- event and source timelines;
- date-window exploration;
- actor/entity/topic browsing;
- report-oriented situational views;
- record drill-down combining source material and derived representations.

### Reject or generalize

- `eval()`-based parsing is unsafe and is not used by the maintained code;
- project-specific OSINT field names are not part of the core visualization contract;
- hard-coded map centers/geography are replaced by data-driven valid coordinates;
- date parsing belongs in shared transforms;
- GIS support must remain optional and ordinary discourse corpora must work without GIS dependencies.

## Maintained design

Issue #18 is implemented around three explicit modes:

- `legacy_ep24`: historical researcher inspection without requiring MongoDB or data migration;
- `canonical_live`: canonical near-real-time monitoring and discourse exploration;
- `hybrid_research`: legacy evidence/intermediate fields and current discourse objects in the same workbench.

Shared map/timeline/report transforms live in `research_views.py` and contain no Streamlit or remote-database side effects. Maps retain `source_url` and provenance, discard invalid/missing coordinates, and never fabricate location data. Timelines keep source, collection, analysis and inferred event time distinct. Generated Markdown/JSON reports remain research aids and can link back to source records when they carry `source_urls`.
