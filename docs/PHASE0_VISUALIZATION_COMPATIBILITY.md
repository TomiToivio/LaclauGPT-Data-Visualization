# Phase 0 visualization compatibility

Issue #62 defines Visualization as a deliberately thin compatibility layer for the
AI26 Phase 0 pipeline.

This document plans the boundary only. It does not create or redesign the hand-built
`laclaugpt/` Phase 0 visualization core described in `PHASE0_FOUNDATION.md`.

## Purpose

Phase 0 Visualization exists to prove that analysis results produced by the minimal
RSS -> MongoDB -> Analysis path can be inspected and exported without activating the
full Phase 1 visualization stack.

The active Phase 0 path should therefore remain:

```text
RSS collection
    ↓
MongoDB: laclaugpt2_<project>_scraper_collection
    ↓
Phase 0 analysis writes phase0.* fields on the same documents
    ↓
thin Visualization reader/exporter
```

Visualization stays downstream. It performs no scraping, LLM inference, discourse
classification, ontology generation, DNA or SNA.

## MongoDB input contract

Phase 0 Visualization should read the same MongoDB database configured for Collection
and Analysis.

Canonical Phase 0 collection naming:

```text
laclaugpt2_<project>_scraper_collection
```

For AI26:

```text
laclaugpt2_ai26_scraper_collection
```

The reader should accept the Collection-style configuration used by the rest of Phase
0:

```text
LACLAUGPT_MONGODB_URI
LACLAUGPT_MONGODB_DATABASE
LACLAUGPT_PROJECT_ID
```

Legacy aliases may be supported only where needed for compatibility, but Phase 0
Visualization should not introduce another configuration framework.

### Source fields

Useful source/document fields already present on the Phase 0 records include:

- `document_id`
- `source_url`
- `source_name`
- `source_type`
- `source_feed_url`
- `source_date`
- `source_title`
- `source_text`
- `source_summary`
- `source_author`
- `source_categories`
- `actor_name`
- `actor_type`
- `arena`
- `ai_formation`
- `political_formation`
- `country`
- `language`
- `collected_at`

Visualization must treat `source_url` as the stable source identity. MongoDB `_id`
is an implementation detail.

### Analysis fields

Phase 0 Analysis writes results back onto the same source document.

The compatibility layer should be prepared to display the fields that already exist,
without inventing new analytical semantics:

- `normalized_text`
- `content_hash`
- `metadata`
- `phase0.preprocess`
- `phase0_summary_raw`
- `phase0_summary`
- `phase0_summary_validated`
- `phase0.summary`
- `phase0.postprocess`
- `phase0_discourse_raw`
- `phase0_discourse`
- `phase0_ontology`
- `phase0.discourse`

A document should count as fully analyzed for the baseline when:

```text
phase0.discourse.status == "ok"
```

Visualization must not reinterpret missing or failed analysis as a substantive
research result.

## Minimal useful Phase 0 surface

The first Phase 0 implementation should be intentionally boring and inspectable.
A CLI/table/export path is sufficient.

### 1. List analyzed documents

Provide a bounded query over the Phase 0 collection with simple filters such as:

- date range;
- actor;
- arena;
- AI formation;
- language;
- analysis status.

Default output should include only a small set of useful columns:

```text
source_date
source_name
actor_name
arena
ai_formation
source_title
source_url
phase0.discourse.status
```

### 2. Inspect one document

Allow selection by `source_url` or `document_id` and show:

- source metadata;
- source text or normalized text;
- validated summary where available;
- Phase 0 discourse fields;
- ontology/export fields where already produced;
- processing statuses and errors.

Raw model payloads may be shown behind an explicit debug/detail option, but they
should not be the default presentation.

### 3. Lightweight summaries

Only summarize fields that Phase 0 already stores. Useful descriptive outputs may
include:

- documents over time;
- counts by actor;
- counts by arena;
- counts by AI formation;
- counts of extracted signifiers/entities when those fields are present in
  `phase0_discourse` or `phase0_ontology`.

These are descriptive counts only. Frequency must not be presented as hegemony,
importance, nodal status or theoretical validity.

### 4. Simple export

Provide at least one lightweight export for debugging and presentation:

- JSONL preserving nested Phase 0 analysis fields; or
- CSV with a deliberately small flattened column set and JSON-encoded nested fields.

Exports should default below `data/exports/` and remain outside Git.

## Error behaviour

Phase 0 should fail plainly rather than silently transform incompatible data.

Examples:

- missing MongoDB URI/database -> clear configuration error;
- missing Phase 0 collection -> clear project/collection error;
- source record missing `source_url` -> display/skip with an explicit warning;
- no `phase0.discourse` -> show "awaiting analysis" rather than fabricating an empty
  result;
- `phase0.discourse.status == "error"` -> expose the stored error status.

A read-only visualization command should return non-zero only for actual execution
or configuration failures, not merely because zero records match a filter.

## Dependencies

The Phase 0 reader/exporter should require only what its task needs.

Required runtime boundary:

- MongoDB / PyMongo;
- Python standard library for CLI and JSON/CSV export.

It must not require:

- Redis;
- CSC Allas / S3;
- multimodal assets or media resolution;
- browser automation;
- distributed task queues;
- Phase 1 graph infrastructure;
- Streamlit or another web framework merely to prove the baseline;
- DNA or SNA.

A later explicitly requested task may add a tiny web/table view around the same reader,
but the MongoDB compatibility layer should remain independently usable from CLI.

## Explicitly deferred to Phase 1+

The following are not part of issue #62:

- canonical nested-record reconstruction;
- Redis caching/pub-sub;
- Allas/S3 artifact loading;
- review workflow;
- provenance editing;
- graph/network exploration;
- temporal graph overlays;
- DNA/SNA visualizations;
- multimodal transcript/OCR/frame views;
- RAG/context visualization;
- full AI26 Streamlit dashboard parity;
- plugin architecture;
- distributed orchestration.

Existing Phase 1 code remains a reference source, not a dependency of the Phase 0
baseline.

## Proposed implementation slices

Follow-up implementation should remain one-purpose-per-issue.

1. **Phase 0 MongoDB reader**
   Read `laclaugpt2_<project>_scraper_collection`, support bounded filters, validate
   required source identity, and expose analyzed/awaiting/error status.

2. **Phase 0 CLI inspection**
   Add list and inspect commands using the reader, with human-readable table/JSON
   output and cron-safe exit behaviour.

3. **Phase 0 export**
   Add JSONL/CSV export under `data/exports/`, preserving nested analysis data
   without inventing a second schema.

4. **Optional minimal presentation view**
   Only after the CLI path works, add a tiny read-only table/detail page if a web
   surface is actually useful.

Each slice should have synthetic tests and no live-service requirement in CI.

## Definition of done for the Phase 0 baseline

The visualization baseline is usable when a researcher can point it at the same
MongoDB deployment used by Phase 0 Collection and Analysis and:

1. list successfully analyzed RSS documents;
2. inspect one document's source, summary and discourse output;
3. filter by simple metadata/date fields;
4. export selected records;
5. do all of the above without Redis, Allas/S3, multimodal files, Phase 1
   orchestration, DNA or SNA.

That is enough to verify Collection -> Analysis -> Visualization end to end. Richer
visual analytics are restored later, one explicit capability at a time.
