# MongoDB graph + vector-capable visualization backend

Issue #20 establishes MongoDB as the preferred shared remote read/query backend while preserving a complete CSV/local path.

## Backend selection

`LACLAUGPT_VIS_STORAGE_BACKEND` accepts:

- `auto` (default): use MongoDB only when a private Mongo URI is configured and reachable; otherwise use the local dataframe path.
- `mongodb`: require MongoDB. Missing/unreachable MongoDB is an explicit error rather than a silent dataset switch.
- `csv`: never attempt MongoDB. CSV/JSON/JSONL/Parquet/SQLite and the existing local analysis-data directory remain usable.

The old `LACLAUGPT_VIS_DATA_BACKEND` setting remains for deployment compatibility. The new storage policy maps onto that maintained loader so existing Streamlit pages do not acquire MongoDB-specific code.

A real MongoDB URI belongs only in `.env` or another private runtime configuration source. `safe_summary()` never returns it.

## Query boundary

`src/laclaugpt_visualization/query_backends.py` owns the storage-neutral query contract:

- `ResearchQueryBackend`
- `CsvQueryBackend`
- `MongoQueryBackend`
- `GraphRequest`
- `ContextRequest`
- `VectorCapability`
- `resolve_query_backend()`

The UI consumes `DataProduct` objects. It does not issue `find`, aggregation, `$graphLookup`, or `$vectorSearch` queries directly. A future Neo4j, ArangoDB or other graph implementation can implement the same query boundary without changing researcher-facing components.

## Durable record parity

Both CSV and MongoDB records pass through the same `normalize_frame()` / `frame_from_records()` boundary. This preserves the existing raw, legacy EP24, intermediate, canonical and newer LaclauGPT fields instead of defining a visualization-specific document schema.

Stable record identity remains `source_url` where available.

## Graph construction

The portable baseline is graph-shaped data already present in canonical research records. The graph builder can represent:

- Record
- Actor / Entity
- Platform
- Location
- Dataset
- Arena
- Signifier
- Frame
- Imaginary
- Topic
- explicit relation endpoints from the canonical `relations` field

Implicit record-to-object edges are descriptive projections of stored fields. Explicit relationship objects preserve their source record, evidence/provenance string where present, and a validation state distinguishing human-validated relations from extracted/inferred ones.

Every graph request is bounded by node count and edge count. Mongo requests additionally bound the number of source records pulled for graph construction. Defaults are deliberately conservative and configurable through non-secret settings:

```text
LACLAUGPT_VIS_GRAPH_MAX_DEPTH=3
LACLAUGPT_VIS_GRAPH_MAX_NODES=500
LACLAUGPT_VIS_GRAPH_MAX_EDGES=1000
```

`MongoQueryBackend.graph_lookup()` provides an optional bounded `$graphLookup` path for deployments that persist shared relation documents with `source_ref` / `target_ref`. It enforces project scoping, maximum depth, maximum returned relations and a server-side query timeout. Embedded record relationships remain the interoperable baseline, so a separate relation collection is not mandatory.

The visualization layer still does not infer hegemony, nodal-point status, empty signification, antagonism or other theoretical categories merely from graph topology. Those objects must come from upstream analysis if displayed as analytical claims.

## Vector search and Context Explorer

MongoDB vector search is capability-aware rather than assumed. The backend checks for the configured search-index name. If it cannot confirm the index, ordinary records and graph views remain available and retrieval is reported as disabled.

Defaults:

```text
LACLAUGPT_VIS_MONGODB_VECTOR_INDEX=laclaugpt_vector
LACLAUGPT_VIS_MONGODB_EMBEDDING_PATH=embedding
LACLAUGPT_VIS_VECTOR_MAX_RESULTS=50
```

For a selected source record, `context()`:

1. verifies vector capability;
2. reads only that record's stored embedding;
3. runs a project-filtered `$vectorSearch` query;
4. excludes the selected record itself;
5. returns bounded neighbouring records plus vector score and safe embedding/version identifiers;
6. exposes stable evidence links through `EvidenceRef`.

It does not place full prompts, private configuration, secrets or arbitrary vector payloads into dashboard metadata.

CSV/local mode intentionally reports vector retrieval as unavailable. A future local vector implementation can be added behind the same contract if there is a concrete need.

## Privacy and security

- Mongo credentials/hosts are private runtime configuration only.
- TLS/authentication options remain part of the private URI or deployment configuration.
- All Mongo record, graph and vector operations are scoped by `project_id`.
- Public fixtures use only `example.invalid` and synthetic identifiers.
- Graph and vector operations have hard limits.
- UI code receives safe query results rather than database clients.

Dataset privacy fields remain part of the canonical record. Deployments that need row-level authorization must enforce it at the service/query boundary rather than relying on hidden Streamlit widgets.

## Relationship to issue #14

Issue #14 remains a possible specialized GraphRAG backend. It is no longer required for standard graph/context operation.

Baseline architecture:

```text
CSV/local files
    -> CsvQueryBackend
    -> shared DataProduct contract

MongoDB
    -> canonical records + analysis
    -> embedded/shared relations
    -> optional vector index
    -> MongoQueryBackend
    -> shared DataProduct contract

future Neo4j / ArangoDB / other graph backend
    -> same query contract
```

This avoids duplicate ETL into a second graph database for ordinary LaclauGPT deployments.
