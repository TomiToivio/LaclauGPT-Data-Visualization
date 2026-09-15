# Canonical data model in Visualization

This repository implements the Visualization-side responsibilities of the project-wide canonical contract owned by [`TomiToivio/LaclauGPT`](https://github.com/TomiToivio/LaclauGPT/blob/main/docs/CANONICAL_DATA_CONTRACT.md).

The architectural boundary is:

```text
canonical record
      ↓
loader / storage adapter
      ↓
canonical reconstruction
      ↓
canonical-to-view-model transform
      ↓
Pandas / charts / Streamlit
```

Pandas columns are a view for human-facing exploration. They are not a second persistent research schema.

## Identity

`source_url` is the canonical record identity, including stable URI-like identifiers for sources without ordinary web URLs. `document_id`, `video_id`, `new_id`, MongoDB `_id`, SQLite primary keys and row numbers are aliases or backend implementation details.

Visualization therefore uses `source_url` for selections, reviews and exports. The view-layer `document_id` field exists only as a compatibility alias and is set to `source_url` whenever canonical identity is available.

## Backend reconstruction

JSON/JSONL is the reference nested representation. Flat adapters such as CSV and simple SQLite tables may encode the canonical `source`, `content`, `analysis`, `review`, `source_native_ids`, `evidence` and `provenance` sections as deterministic JSON strings. `canonical.reconstruct_canonical()` decodes those sections before any visualization semantics are applied.

Mongo-like documents may remain nested. Backend `_id` values are discarded at the view boundary and do not replace canonical identity. Parquet may contain nested structures directly or deterministic JSON-encoded sections, depending on the writer.

All timestamps used by the DataFrame view are normalized to timezone-aware UTC by Pandas. The persisted canonical record remains available as `raw_record`, including the original timestamp strings/offsets.

Missing optional lists become empty lists in the view. Missing multimodal material is not fabricated. A text-only source is a first-class record.

## Source metadata

The view exposes the canonical source concepts inherited from the project-wide contract and CyborgAnthropology lineage:

- source URL / URI
- source text
- platform and source/content type
- author and author full name
- source-created timestamp
- collection timestamp
- collector and collection method
- language and country
- raw metadata/raw reference where safe
- media and file references

Storage backends do not rename these concepts.

## Analysis metadata

The view understands canonical analysis fields including entities and mentions, topics, classifications, formations, signifiers, nodal points, discourses, imaginaries, Us/Them/frontier elements, affects, sentiments, relations, Formula of Populism material, uncertainty, abstentions, model runs, evidence, provenance and review state.

Descriptive computation remains distinct from theoretical claims. Counts, graph degree, semantic similarity, sentiment and layout do not establish hegemony, nodal status, empty/floating signification, equivalence, antagonism or a valid political frontier by themselves.

## Human review

The typed `Review` model is keyed by canonical `source_url`. SQLite and MongoDB review stores expose the same logical model. Researcher notes, corrections and rerun/reprocess requests therefore remain attached to the same source identity regardless of persistence backend.

## Legacy EP24 compatibility

Historical EP24 flat fields are handled only in `legacy_ep24.py`. The adapter maps useful values into the common view model and keeps historical IDs as `source_native_ids`. Numbered OCR/frame fields are collected into structured view collections. Text-only records do not receive artificial frame or transcript content.

Legacy vocabulary must not spread into core canonical code.

## Repository archaeology

The issue implementation audited the main schema and visualization lineages and classified them as follows:

| Source | Classification | Reuse decision |
| --- | --- | --- |
| `TomiToivio/LaclauGPT/docs/CANONICAL_DATA_CONTRACT.md` | `ADOPT` | Normative identity, nested sections, storage-neutral semantics and review rules. |
| `TomiToivio/CyborgAnthropology/src/models.py` | `ADAPT` | Preserve its useful universal source concepts (`scraper_url`, text, type, created/scraped time, collector, local/Allas references) through the canonical names owned by LaclauGPT. |
| current `LaclauGPT-Data-Collection` | `ALREADY_IMPLEMENTED` | Consume its canonical records; never import its implementation internals. |
| current `LaclauGPT-Data-Analysis` | `ALREADY_IMPLEMENTED` | Consume analysis-enriched canonical records and evidence/provenance; never import analysis internals. |
| `LaclauGPT-Discourse-Analysis` | `ADAPT` | Preserve evidence-first discourse fields and dashboard behavior through canonical analysis fields, not the former monolithic package structure. |
| `LaclauGPT-Multimodal-Analysis` | `LEGACY_COMPATIBILITY_ONLY` | Retain transcript/OCR/frame/media/summary semantics through the isolated EP24 adapter. The old sequential Puhti pipeline is not the new architecture. |
| `LaclauGPT-TikTok-Scraper` | `LEGACY_COMPATIBILITY_ONLY` | Historical source/media identifiers may be retained as aliases; scraper architecture does not belong in Visualization. |
| `ep2024_postprocess` and EP24 dashboard lineage | `LEGACY_COMPATIBILITY_ONLY` | Human-readable EP24 fields remain readable through the adapter without becoming canonical columns. |
| private research repositories | `PRIVATE_DO_NOT_COPY` | They may be inspected only when authorized to understand behavior. Data, configuration, credentials, target lists and private study content must never be copied here. |
| giant historical dashboard scripts | `OBSOLETE` | Functionality should be decomposed into loaders, canonical adapters, transforms, review persistence and UI orchestration. |

The goal is behavioral continuity without resurrecting the old monolith.

## Contract tests

`tests/test_cross_backend_contract.py` uses synthetic data only and verifies equivalent visualization semantics for:

- nested Pandas/Python records;
- JSONL;
- CSV with JSON-encoded canonical sections;
- SQLite with JSON-encoded canonical sections;
- Mongo-like documents without a live MongoDB service;
- text-only records;
- legacy EP24 identity and multimodal mapping.

Normal CI must not require live MongoDB, Redis, S3/Allas, Ollama or real research data.
