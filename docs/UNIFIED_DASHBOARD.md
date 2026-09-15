# Unified dashboard architecture

`LaclauGPT-Data-Visualization` exposes one application with shared loaders, filters, transforms and review state.

## Monitor

Monitor is the generalized AI26-style situational-awareness view. It shows corpus size, analyzed/awaiting-analysis counts, latest source and analysis timestamps, formations, signifiers, actors and other descriptive summaries. Local files may be refreshed by Streamlit reruns; distributed deployments may use MongoDB/Redis, but polling is sufficient and remote services are optional.

## Researcher Review

Researcher Review is the generalized EP24-style workbench. One canonical record is selected by `source_url`; the page shows source metadata, human-readable summary, transcript, OCR, frame/multimodal references, structured analysis, uncertainty/abstention and provenance.

Review state is separate from canonical analysis output. `Review` supports status, dubious/exclusion/wrong-language flags, corrected fields, researcher note, analysis/ASR/OCR rerun requests, media reprocessing, split/cut request metadata and review version. SQLite under `data/database/reviews.sqlite3` is the local default. `MongoReviewStore` is an optional adapter for distributed teams and performs no connection at import time.

Visualization requests reruns but never performs them.

## Explore

Explore uses the same filtered frame to build timelines, formation/topic/entity/signifier distributions, relation tables and graph-projection inputs. Exported/filtered data remains runtime research material and belongs under `data/exports/`.

## Canonical input

`canonical.py` understands the public nested record contract and flattens only presentation fields. The canonical `source_url` remains the record identity. Schema version, timestamps, provenance, review status, uncertainty/abstention and multimodal references remain visible.

`legacy_ep24.py` is the only place where historical EP24 columns are interpreted. It maps useful fields into the common view model and tags them with adapter provenance.

## Storage profiles

Local operation uses CSV/JSON/JSONL/SQLite/local filesystem. The configured `analysis_data_dir` supports same-machine Analysis → Visualization access without guessing repository locations.

Distributed operation may use MongoDB for canonical records, Redis for shared cache/pub-sub/state, and S3-compatible storage such as CSC Allas for referenced artifacts. None are required for import, unit tests or laptop operation.

## Privacy

All real datasets, researcher notes, review databases, uploaded files, exports, caches and operational configuration stay under ignored `data/` or external private systems. `.streamlit/` is ignored. Public examples and tests are synthetic.

## Interpretation rule

A visualization is not an inference engine. Frequency, co-occurrence, graph degree, layout and model confidence are descriptive properties of the collected/analysed corpus. They are not automatic evidence of hegemony, nodal status, empty/floating signification, equivalence, antagonism or political-frontier validity.
