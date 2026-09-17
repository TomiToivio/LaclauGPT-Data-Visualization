# Research UI and plugin architecture

LaclauGPT Data Visualization is the researcher-facing shell for the platform, not only a chart renderer. Data Collection owns acquisition, Data Analysis owns analytical logic, and this repository owns how researchers browse, inspect, visualize, query and, when authorized, orchestrate those capabilities.

## Standard logical products

`laclaugpt_visualization.products` defines backend-independent product types:

- `table` and `records`
- `knowledge_graph` and `network`
- `geodata`
- `timeline`
- `retrieval` for vector/GraphRAG contexts
- `report`
- `media`

A `ProductProvider` advertises capabilities and returns `DataProduct` objects. Providers may be implemented by CSV/Parquet/Pandas, MongoDB, SQLite, NetworkX/igraph, GeoJSON, vector indexes, Allas/S3 references or future storage backends. Plugins depend on logical product capabilities rather than database-specific APIs.

`EvidenceRef` is the common drill-down primitive. Analytical products should attach record IDs and, where allowed, source/artifact references so a graph edge, map point, chart value, report claim or RAG answer can lead back to supporting evidence.

## Exactly two top-level plugin kinds

`laclaugpt_visualization.plugins` exposes two public extension kinds:

1. **Visualization plugins** are read-only representations. They may zoom, filter, select, drill down and export, but cannot mutate canonical data, configuration, jobs or external state.
2. **User-interface plugins** handle researcher workflow and control-plane interaction: annotation, notes, MongoDB edits, Redis configuration, task queues, RAG/agent chat and operational controls.

The older `PluginKind.INTERACTION` and `PluginKind.RESEARCH_ASSISTANT` identifiers from issue #22 remain compatibility aliases of `USER_INTERFACE`; they are not additional top-level plugin kinds.

`PluginCategory` provides finer grouping such as core, temporal, network, geospatial, multimodal, legacy, research workflow, data management, configuration, tasks, chat/agent and operations.

Each `PluginSpec` may declare:

- stable plugin ID/name and version;
- top-level kind and category;
- required logical products;
- required/optional record fields;
- required backend capabilities such as `mongodb`, `redis_config`, `redis_task_queue` and `redis_message_queue`;
- dashboard modes;
- permissions;
- interactions/exports;
- privacy level;
- whether it mutates state;
- whether confirmation and auditing are required;
- whether RAG is required;
- whether the renderer is currently a documented placeholder;
- provenance to maintained/legacy source code.

The registry rejects a visualization plugin that claims to mutate state, and rejects a state-changing UI plugin that does not require auditing.

## Capability gating

`PluginRegistry.status()` evaluates products, record fields, backend capabilities, dashboard mode and RAG availability and returns explicit missing requirements. `PluginRegistry.available()` filters the catalog using the same rules.

The Streamlit **Plugin Library** tab displays this availability information for the current dataframe and deployment. Optional MongoDB/Redis/RAG features therefore degrade to "unavailable" rather than preventing local/offline startup.

## Current catalog

The first-party catalog contains maintained/adapted components and explicit future contracts, including:

- dataframe, record/evidence, monitor, distributions, cross-tabs and data-quality views;
- timeline, trends, reports and temporal comparisons;
- generic/discourse/actor/bipartite networks, graph deltas, Sankey and embedding views;
- maps, map+timeline, media and multimodal evidence;
- EP24 legacy, orbital data-art and pledge-dashboard special views;
- search, researcher review, ethnography/research notes, codebook/config inspection;
- Mongo editing/quarantine/bulk operations and exports;
- distributed settings, task launch/monitor, URL ingestion and batch reprocessing;
- RAG chat/evidence, agent console, backend status and plugin manager.

See `docs/PLUGIN_INVENTORY.md` for source-by-source legacy mapping and reuse decisions.

## Local/simple mode

The architecture does not require MongoDB, Redis, RAG, authentication or agents. `InMemoryProvider` supplies a tiny reference provider, and CSV/Pandas-based providers can expose the same product contract. A laptop workflow can remain:

```text
CSV/Parquet -> provider -> visualization plugins -> local dashboard
```

Local review and research-note persistence can use SQLite. Distributed plugins simply report unmet backend capabilities.

## Service boundaries

The UI must not import collection or analysis internals. `laclaugpt_visualization.workbench` defines Collection/Analysis service ports and the permission/audit broker.

`laclaugpt_visualization.services` adds initial injected adapters for issue #26:

- `MongoRecordService`: whitelist-only derived/review edits plus recoverable quarantine;
- `RedisConfigService`: versioned namespaced distributed settings with stale-form checking and secret-key rejection;
- `RedisTaskQueueService`: structured work envelopes and idempotency/task IDs;
- `RedisMessageQueueService`: structured RAG/agent message envelopes with explicit dashboard context;
- `SQLiteNotesStore`: local-first research and digital-ethnography notes with tags/evidence links.

These adapters accept existing client objects. Importing them creates no network connections. Deployment code is responsible for constructing clients from private runtime configuration.

## Permissions and auditability

The permission vocabulary includes:

`view`, `annotate`, `edit_derived_data`, `edit_collection_config`, `edit_analysis_config`, `run_collection`, `run_analysis`, `export`, `soft_delete_exclude`, `physical_delete`, and `admin`.

Read-only is the default. Mutating actions require explicit permissions. Brokered mutations record actor, timestamp, project, action, target/job references, before/after information where applicable and an optional reason. Human and agent actions remain distinguishable.

Physical deletion is intentionally separate from recoverable exclusion/quarantine. The issue-#26 Mongo adapter does not expose a generic physical-delete method.

## RAG and research agents

RAG is an optional UI capability built on the `retrieval` logical product and/or Redis message boundary. Implementations must surface retrieved evidence/provenance and distinguish source observations from generated synthesis. Project/privacy filtering belongs in provider/service layers so a plugin cannot bypass it.

Agents use the same service ports and permissions as humans. They should be read-only unless granted mutation rights. Expensive/destructive actions require explicit target previews/confirmation at the UI layer and jobs remain observable rather than hidden background work.

## Notes and writing workspace

Research notes and digital ethnography are first-class UI plugins linked to project/record/evidence context. This repository provides storage/service boundaries and evidence insertion/export hooks rather than becoming a bespoke word processor.

## Frontend direction

Keep Streamlit for the current researcher workbench and use Components v2 only where richer browser components are genuinely needed. Plotly remains the default chart layer. Candidate custom libraries include Cytoscape.js or Sigma/Graphology for networks, MapLibre/deck.gl for richer geospatial work, AG Grid for advanced tables, TipTap for structured notes and Monaco only for advanced raw configuration editing.

If complex distributed state eventually fights Streamlit's rerun model, evaluate Plotly Dash as a Python-first middle path or FastAPI + React/TypeScript as the long-term application architecture. The product/plugin/service boundary is intentionally frontend-portable. See `docs/FRONTEND_STACK.md`.

## Interpretation rule

Visualization displays collected/analysed structure. It must not silently turn counts, co-occurrence, graph degree/layout, embeddings or model confidence into claims of hegemony, nodal status, empty/floating signification, equivalence, antagonism or political-frontier validity. Those require explicit upstream analysis and human interpretation.
