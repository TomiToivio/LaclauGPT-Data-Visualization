# Research UI and plugin architecture

LaclauGPT Data Visualization is the **researcher-facing shell for the whole platform**, not only a chart renderer. Data Collection owns acquisition, Data Analysis owns analytical logic, and this repository owns how researchers browse, inspect, visualize, query and, when authorized, orchestrate those capabilities.

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

## Plugin classes

`laclaugpt_visualization.plugins` separates three extension categories:

1. **Visualization plugins** render analytical products.
2. **Interaction/UI plugins** provide search, annotation, configuration and job controls.
3. **Research-assistant plugins** provide grounded RAG, agents, notes and writing integrations.

Each `PluginSpec` declares a name, version, category, required product capabilities, orientation, interactions, exports, config schema, permissions and whether RAG is required. `PluginRegistry` handles registration, discovery and explicit missing-capability errors.

First-party descriptors currently establish independent `table`, `map`, `timeline`, `network`, `global_search` and `rag_evidence` plugins. Existing Streamlit and legacy dashboards remain compatible views and can be migrated behind these interfaces incrementally.

A minimal plugin can be registered without any Laclau-specific columns:

```python
from laclaugpt_visualization.plugins import PluginKind, PluginSpec, RegisteredPlugin
from laclaugpt_visualization.products import ProductKind

plugin = RegisteredPlugin(
    PluginSpec(
        name="my-view",
        version="1.0",
        kind=PluginKind.VISUALIZATION,
        requires=frozenset({ProductKind.TABLE}),
    ),
    render=my_render_function,
)
```

## Local/simple mode

The architecture does not require MongoDB, Redis, RAG, authentication or agents. `InMemoryProvider` supplies a tiny reference provider, and CSV/Pandas-based providers can expose the same product contract. A laptop workflow can therefore remain:

```text
CSV/Parquet -> provider -> table/network/map/timeline plugin -> local dashboard
```

RAG plugins are simply unavailable when `rag_enabled=False`; the rest of the UI remains usable.

## Full-system service boundaries

The UI must not import collection or analysis internals. `laclaugpt_visualization.workbench` defines `CollectionService` and `AnalysisService` ports. Concrete HTTP, CLI, Redis/job-queue or local adapters can implement those interfaces later without changing plugins.

`ActionBroker` is the authorization/audit boundary for operations initiated from the UI or an agent. It currently covers analysis/collection runs and config mutations and is intentionally small so additional destructive actions can follow the same pattern.

## Permissions and auditability

The permission vocabulary includes:

`view`, `annotate`, `edit_derived_data`, `edit_collection_config`, `edit_analysis_config`, `run_collection`, `run_analysis`, `export`, `soft_delete_exclude`, `physical_delete`, and `admin`.

Read-only is the default. Mutating actions require an explicit permission. Every brokered mutation records an `AuditEvent` with actor ID/type, timestamp, project, action, target/job references, before/after data where applicable and an optional reason. Human and agent actions are explicitly distinguishable.

Physical deletion should always be implemented separately from soft exclusion and should preserve an audit trail consistent with project policy.

## RAG and research agents

RAG is an optional research-assistant capability built on the `retrieval` logical product. Implementations must surface retrieved evidence/provenance and distinguish source observations from generated synthesis. Project/privacy filtering belongs in the provider/service layer so a plugin cannot accidentally bypass it.

Agents use the same service ports and permissions as humans. They should be read-only unless granted mutation rights, and expensive/destructive actions should support preview/confirmation at the UI layer. Jobs must remain observable rather than hidden as background work.

## Notes and writing workspace

Research notes and paper/report authoring should be implemented as plugins or integrations over the same record/evidence links. This repository should provide the workbench boundary, evidence insertion and export hooks, not become a bespoke word processor.

## Incremental implementation path

The foundation in this issue corresponds to the first architectural slice: standard products, plugin registry, first-party plugin descriptors, service boundaries, permissions, audit events and local/RAG-disabled behavior. The existing dashboard remains operational while concrete renderers, server adapters, annotation/edit flows, grounded chat, job monitoring and notes/writing plugins are layered on incrementally.
