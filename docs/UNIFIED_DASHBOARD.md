# Unified dashboard architecture

`LaclauGPT-Data-Visualization` exposes one application with shared loaders, filters, transforms and review state. The application now has three explicit modes rather than separate monolithic dashboards.

## Dashboard modes

### `legacy_ep24`

For historical EP24-style CSV/dataframe exports. The legacy adapter preserves original columns and maps useful fields into the common visualization model, so historical datasets can be inspected without rewriting them or requiring MongoDB. The main workflow is researcher review, dense research-data inspection, timeline/map views when data exists, and generated reports.

### `canonical_live`

For current canonical LaclauGPT records and near-real-time AI26-style monitoring. It exposes corpus monitoring, discourse exploration, researcher review, timeline/map views, reports and the full research dataframe. The UI reads analysis results; it does not perform discourse analysis itself.

### `hybrid_research`

For datasets that contain both historical/intermediate EP24-style fields and current canonical analysis. This mode combines the old researcher workflow with current formations, signifiers, relations, discourse graphs, timelines, maps and reports while keeping the same `source_url` identity across views.

The application infers a useful default mode from the loaded data, but researchers may switch modes explicitly from the sidebar.

## Monitor

Monitor is the generalized AI26-style situational-awareness view. It shows corpus size, analyzed/awaiting-analysis counts, latest source and analysis timestamps, formations, signifiers, actors and other descriptive summaries. Local files may be refreshed by Streamlit reruns; distributed deployments may use MongoDB/Redis, but polling is sufficient and remote services are optional.

## Researcher Review

Researcher Review is the generalized EP24-style workbench. One canonical record is selected by `source_url`; the page shows source metadata, human-readable summary, transcript, OCR, frame/multimodal references, structured analysis, uncertainty/abstention and provenance.

Review state is separate from canonical analysis output. `Review` supports status, dubious/exclusion/wrong-language flags, corrected fields, researcher note, analysis/ASR/OCR rerun requests, media reprocessing, split/cut request metadata and review version. SQLite under `data/database/reviews.sqlite3` is the local default. `MongoReviewStore` is an optional adapter for distributed teams and performs no connection at import time.

Visualization requests reruns but never performs them.

## Explore

Explore uses the same filtered frame to build timelines, formation/topic/entity/signifier distributions, relation tables and graph-projection inputs. Exported/filtered data remains runtime research material and belongs under `data/exports/`.

## Timeline and map

`research_views.py` provides pure, storage-neutral transforms for temporal and geospatial exploration.

The timeline keeps four clocks distinct when available:

- source/publication time;
- collection time;
- analysis time;
- extracted/inferred event time.

These times are never silently collapsed into one field.

Map points are emitted only when valid coordinates already exist in the record. Coordinates outside valid latitude/longitude ranges are discarded, missing coordinates are not guessed, and each point retains `source_url` plus available provenance. The current Streamlit view uses Plotly geographic scatter, so no GIS dependency is required for ordinary installations.

## Daily / research reports

Generated Markdown and JSON reports can be placed under ignored `data/reports/`. The dashboard indexes them by date and renders the selected report. JSON reports may include `source_urls` so claims/items can link back to records in the current filtered corpus.

Report rendering does not elevate generated text to a research finding: reports remain research aids that require human verification.

## Canonical input

`canonical.py` understands the public nested record contract and flattens only presentation fields. The canonical `source_url` remains the record identity. Schema version, timestamps, provenance, review status, uncertainty/abstention and multimodal references remain visible.

`legacy_ep24.py` is the only place where historical EP24 columns are interpreted. It maps useful fields into the common view model and tags them with adapter provenance.

The historical code audit is documented in [`LEGACY_DASHBOARD_AUDIT.md`](LEGACY_DASHBOARD_AUDIT.md). In particular, hard-coded credentials, import-time database connections, unsafe parsing, global state and monolithic UI/storage logic are deliberately not carried forward.

## Storage profiles

Local operation uses CSV/JSON/JSONL/SQLite/local filesystem. The configured `analysis_data_dir` supports same-machine Analysis → Visualization access without guessing repository locations.

Distributed operation may use MongoDB for canonical records, Redis for shared cache/pub-sub/state, and S3-compatible storage such as CSC Allas for referenced artifacts. None are required for import, unit tests or laptop operation.

## Privacy

All real datasets, researcher notes, review databases, uploaded files, reports, exports, caches and operational configuration stay under ignored `data/` or external private systems. `.streamlit/` is ignored. Public examples and tests are synthetic.

## Interpretation rule

A visualization is not an inference engine. Frequency, co-occurrence, graph degree, layout and model confidence are descriptive properties of the collected/analysed corpus. They are not automatic evidence of hegemony, nodal status, empty/floating signification, equivalence, antagonism or political-frontier validity.
