# Dashboard plugin inventory

This inventory implements the audit requested by issue #26. The maintained plugin catalog lives in `laclaugpt_visualization.plugins`; this document records where the reusable behaviors came from and what must remain isolated.

## Architectural rule

There are two top-level plugin kinds:

- **visualization**: read-only representation of research data/products. Zoom, filtering, selection and drill-down are allowed, but the plugin does not mutate canonical data, configuration or queues.
- **user interface**: researcher/control-plane interaction. These plugins may annotate, edit, enqueue or message only through explicit service adapters with permission, confirmation and audit requirements.

The old issue-#22 `interaction` and `research_assistant` labels are compatibility aliases of `user_interface`, not a third/fourth top-level kind.

## Current maintained dashboard

| Source | Reusable behavior | Catalog plugins | Reuse strategy | Caveats |
| --- | --- | --- | --- | --- |
| `src/laclaugpt_visualization/app.py` Monitor | corpus counts, analyzed/pending state, formations/signifiers/actors | `corpus_monitor`, `distributions` | keep current renderer; migrate behind registry incrementally | descriptive counts are not theoretical inference |
| `app.py` Researcher Review + `review.py` | source drill-down, transcript, OCR, frame analysis, structured analysis, review flags/notes/rerun requests | `record_evidence`, `multimodal_evidence`, `researcher_review` | reuse maintained implementation | review mutation must remain separate from canonical analytical output |
| `app.py` Research Data | dense dataframe inspection | `table` | reuse maintained implementation | large-table enhancements may later use AG Grid |
| `research_views.timeline_counts` | source/collection/analysis/event clocks | `timeline`, `temporal_compare`, `trends` | directly reuse transform | never collapse the four clocks silently |
| `research_views.map_points` | valid geospatial evidence with source identity | `map`, `map_timeline` | directly reuse transform | never infer/fabricate coordinates |
| `app.py` Reports + `research_views.load_reports` | Markdown/JSON reports and linked records | `reports` | reuse | generated reports remain research aids |
| `transforms.graph_projection` / `relations` | relation projection and graph inputs | `network`, future `discourse_graph` | reuse current transform and extend contracts | graph layout/degree is not automatic evidence of hegemony/nodal status |
| `canonical.py`, `legacy_ep24.py` | canonical and legacy adapter boundary | all data-facing plugins | preserve | plugin code should not interpret old columns independently |

## Historical EP24 dashboards

### `TomiToivio/ep2024_postprocess/dashboard/dashboard.py`

Useful behavior:

- dense researcher table and stable-record selection concept;
- transcript, translation, OCR, frame/multimodal inspection;
- historical themes/entities/sentiment/topics/ManifestoBERTa/Formula-of-Populism displays;
- researcher review flags and rerun requests;
- helper chart ideas such as category counts and stacked daily views.

Catalog mapping: `table`, `record_evidence`, `multimodal_evidence`, `distributions`, `legacy_ep24`, `researcher_review`.

Do **not** copy the monolith. The audited historical implementation contains hard-coded MongoDB credentials, import-time database access, global Streamlit state, mixed local-JSON/Mongo review persistence and private-record logging. Any still-valid historical credential should be treated as compromised and rotated outside this repository.

### `LaclauGPT-Discourse-Analysis-Private/KEEP_PRIVATE/ep24/dashboard.py`

Useful behavior: private researcher inspection of canonical EP24 re-analysis output. Reuse the workflow concepts through the maintained `legacy_ep24.py` adapter and `record_evidence` / `researcher_review` plugins. Do not move private datasets or private project configuration to this public repository.

### Private `laclaugpt/visualization/` dashboards

Useful behavior: canonical dashboard, near-real-time AI26 dashboard, launcher, project/profile-aware Streamlit patterns. These informed the current maintained `canonical_live` and `hybrid_research` modes. Prefer the maintained code already migrated into this repository rather than importing private modules at runtime.

## Legacy art visualization

`LaclauGPT-Discourse-Analysis-Private/KEEP_PRIVATE/experimental/legacy_art_visualization/` contains the EP24 orbital/cyberspace data-art concept. Preserve it as an isolated `legacy_art` plugin/placeholder with an explicit input contract. It is intentionally not part of the canonical analysis pipeline.

## VASAMA/OSINT legacy dashboard

Useful generalized concepts:

- one/many-event maps;
- event/source timelines and date windows;
- actor/entity/topic browsing;
- report-oriented situational views;
- record drill-down linking raw evidence to derived representations.

Catalog mapping: `map`, `map_timeline`, `timeline`, `reports`, `record_evidence`.

Reject/generalize historical assumptions: project-specific OSINT fields, hard-coded map centers, unsafe `eval()` parsing and UI-specific storage access. GIS remains optional.

## Visualization catalog

Implemented descriptors represent the expected library even where the renderer is intentionally a placeholder pending upstream data products:

- core: `table`, `record_evidence`, `corpus_monitor`, `distributions`, `crosstab_heatmap`, `data_quality`;
- time/change: `timeline`, `trends`, `reports`, `temporal_compare`;
- networks/discourse: `network`, `discourse_graph`, `actor_network`, `bipartite_network`, `graph_delta`, `sankey`, `embedding`;
- geospatial/multimodal: `map`, `map_timeline`, `media_gallery`, `multimodal_evidence`;
- legacy/special: `legacy_ep24`, `legacy_art`, `pledge_dashboard`.

A placeholder is a real contract, not an empty file. Its registry metadata states which logical products/backend capabilities it will need. Upstream Analysis remains responsible for computing embeddings, discourse objects, communities, temporal graph deltas, etc.; Visualization displays them.

## User-interface catalog

Research workflow:

- `global_search`
- `researcher_review`
- `ethnography_notes`
- `research_notes`
- `codebook_editor`
- `config_inspector`

Data management:

- `mongodb_editor`
- `record_quarantine`
- `bulk_edit`
- `export_snapshot`

Distributed configuration/tasks:

- `distributed_settings`
- `task_launcher`
- `task_monitor`
- `url_ingest`
- `batch_reprocess`

Chat/agent/operations:

- `rag_chat`
- `rag_evidence`
- `agent_console`
- `backend_status`
- `plugin_manager`

## Service boundaries

`src/laclaugpt_visualization/services.py` provides safe initial adapters:

- `MongoRecordService`: whitelist-only derived/review edits and recoverable quarantine; no connection at import time and no generic physical-delete API.
- `RedisConfigService`: namespaced, versioned JSON settings with stale-form detection and rejection of secret-like keys.
- `RedisTaskQueueService`: structured task envelopes with task/idempotency IDs; the dashboard enqueues work rather than running collection/analysis inline.
- `RedisMessageQueueService`: structured RAG/agent messages with explicit dashboard context; no shell/process access.
- `SQLiteNotesStore`: local-first timestamped research/ethnography notes with tags and evidence links.

Concrete deployment code should create the MongoDB/Redis clients from private runtime settings and inject them into these adapters. The module itself stays import-safe in local/offline mode.

## Adding a plugin

1. Decide whether it is **visualization** or **user_interface**. If it mutates state, it is UI.
2. Add a `PluginSpec` through the catalog helper with a stable ID, product requirements, fields, modes and optional backend capabilities.
3. For state-changing UI, declare permissions, `mutates=True`, confirmation where needed, and `audit=True`. The registry rejects a mutating plugin without auditing.
4. Keep transforms storage-neutral and avoid direct Mongo/Redis calls in renderer code.
5. If upstream output does not exist yet, register a documented placeholder rather than inventing analytical semantics in Visualization.
6. Add synthetic tests for capability gating and mutation safety. Never commit private data, credentials or operational `.env` files.
