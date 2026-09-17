# AI26 distributed research dashboard

The AI26 dashboard is a private researcher-facing Streamlit workbench built on the existing LaclauGPT Visualization contracts. It does not create a Visualization-only research schema.

## Contract audit

The current distributed Analysis contract publishes Collection handoff data to the project `records` collection, durable successful analysis to `analyzed`, and in-flight/failure state to `processing`. Visualization therefore reads:

```text
ai26__records
ai26__analyzed
ai26__processing
ai26__relations
ai26__reviews
ai26__runs
```

Redis remains coordination infrastructure, never the durable research source of truth. The AI26 dashboard uses the shared `ProjectNamespace` contract:

```text
laclaugpt:ai26:settings:visualization:current
laclaugpt:ai26:stream:config-events
laclaugpt:ai26:stream:messages:rag
```

The RAG request envelope preserves `project_id`, `request_id`, `correlation_id`, sender/recipient, message type and timestamp. Returned source/evidence identifiers are displayed exactly as received. Large evidence payloads belong in MongoDB/files/object storage and should be referred to by stable IDs.

## Private Linux profile

Use a private runtime `.env`, systemd EnvironmentFile, secret manager or equivalent. Never commit real endpoints or credentials.

```text
LACLAUGPT_VIS_PROFILE=server
LACLAUGPT_VIS_MACHINE=linux-server
LACLAUGPT_VIS_EXECUTION=web-service
LACLAUGPT_VIS_STORAGE=distributed
LACLAUGPT_VIS_PROJECT_ID=ai26
LACLAUGPT_VIS_STORAGE_BACKEND=mongodb
LACLAUGPT_VIS_DATA_BACKEND=mongodb
LACLAUGPT_VIS_CACHE_BACKEND=redis
LACLAUGPT_VIS_MESSAGING_BACKEND=redis
LACLAUGPT_VIS_OBJECT_BACKEND=s3
LACLAUGPT_VIS_SERVER_HOST=127.0.0.1
LACLAUGPT_VIS_SERVER_PORT=8501
LACLAUGPT_VIS_MONGODB_URI=<private>
LACLAUGPT_REDIS_URL=<private>
LACLAUGPT_VIS_S3_ENDPOINT_URL=<private>
LACLAUGPT_VIS_S3_BUCKET=<private>
```

Start with:

```bash
bash scripts/run_ai26_dashboard.sh
```

or, equivalently, through the production CLI — for a `project_id=ai26` profile
`serve` launches this same module:

```bash
.venv/bin/laclaugpt-visualize serve
```

The launcher binds to loopback by default, runs headless, keeps XSRF/CORS protections enabled, and refuses a non-AI26 project ID. Authentication is intentionally not implemented by issue #34. Do **not** expose the process to the public Internet. Use host/network restrictions now; add authenticated reverse-proxy access before any wider exposure.

## Information architecture

The dedicated workbench provides:

- **Monitor**: durable collected/analyzed/processing counts, bounded live window, ingestion/analysis time views and descriptive distributions.
- **Explore**: formations, topics, entities and formation × signifier tables while preserving multi-label assignments.
- **Networks**: existing `GraphProjection`/relation outputs only. Visualization does not infer new equivalence, hegemony or antagonism.
- **Records**: searchable/filterable table plus close reading of text, analysis, uncertainty, abstention and safe provenance.
- **Reports**: existing generated periodic reports and evidence links.
- **RAG Chat**: Redis Streams client for the upstream AI26 retrieval service. Visualization does not implement its own model/RAG engine.
- **Configuration**: sanitized effective config plus an allowlisted Visualization-only `config.publish` proposal path. Collection/Analysis settings and secrets remain read-only.
- **Hermes**: existing bounded Visualization Hermes operations such as safe config inspection and local derived-cache maintenance. No shell is exposed.
- **Diagnostics**: canonical collection/key names, bounded query duration, last load, worker/event availability and safe runtime configuration.

## Global filtering

Current coordinated filters cover text search, source/platform, language, country/region and multi-label formation. The filter state is passed to RAG as optional retrieval scope. Additional arena/topic/entity/revision controls should be added when those fields are stable in the canonical upstream schema rather than guessed in Visualization.

## Real-time behavior

The current implementation uses bounded near-real-time durable reads from MongoDB and optional Redis operational signals. It deliberately favors correctness and reconnect simplicity over making Redis a data store. The loaded live window defaults to 500 and is capped at 5,000 records in the UI.

The UI exposes a refresh target and explicit refresh control. A later optimization may add MongoDB change streams when the private deployment topology guarantees replica-set/change-stream support. Until then, durable bounded reads avoid making deployment depend on that feature.

## Multimodal boundary

No image, video or audio blobs are fetched for display. Textual metadata and upstream-derived multimodal analysis may be shown because those are analysis outputs, not media viewing. Allas/S3 remains available to the wider stack for canonical artifacts, but this dashboard does not download media merely to render it.

## Configuration safety

Only the following Visualization-owned settings can be proposed by the dashboard today:

- `refresh_seconds`
- `default_time_range_days`
- `graph_max_nodes`
- `graph_max_edges`
- `vector_max_results`
- `enabled_plugins`

Publishing creates a project-scoped `config-events` stream message. The receiving module must validate and apply the change. The dashboard does not silently mutate arbitrary files, MongoDB research records, Collection/Analysis configuration, credentials or shared Redis state.

## Performance and data volume

- MongoDB reads are project-scoped and bounded.
- Durable collection totals use MongoDB counts rather than loading the whole corpus.
- Tables and graph projections are capped by the loaded window and existing graph limits.
- Redis is used only for small operational/config/RAG messages.
- No full-corpus or multimodal download is required for the dashboard process.
- Query duration, page size and last-load timestamp are visible in Diagnostics.

## Tests

`tests/test_issue34_ai26_dashboard.py` is entirely offline. It checks:

- `project_id=ai26` isolation;
- current `records` / `processing` / `analyzed` Mongo names;
- canonical Redis keys/streams;
- multi-label formation preservation;
- bounded shared filtering;
- allowlisted config publishing;
- RAG correlation IDs and returned evidence IDs.

Live MongoDB, Redis, RAG or model services are not required by CI.
