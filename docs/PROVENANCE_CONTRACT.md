# Analysis and effective-run provenance in Visualization

Visualization is a **consumer** of Collection/Analysis provenance. It does not execute
codebooks, assemble LLM context, load private prompts, or reconstruct effective project
configuration. The dashboard only projects safe identifiers and fingerprints emitted with
records/runs.

Missing fields are displayed as `unknown / not recorded`. This is especially important for
EP24 and other legacy exports: absence of provenance is not interpreted as a default profile.

## Data-contract audit

| field | producer | canonical location | dashboard surface | legacy fallback |
|---|---|---|---|---|
| `run_id` | Analysis | provenance event / run metadata | record inspector, filters, mixed-version warning | unknown |
| `study_id` / `project_id` | Collection / Analysis | provenance event / canonical record metadata | record inspector | unknown |
| `arena` | Collection / Analysis | provenance event / study metadata | record inspector | unknown |
| `dataset` | Collection | provenance event / collection metadata | record inspector | unknown |
| `country`, `language` | Collection | `source` plus provenance when emitted | record inspector | canonical source aliases |
| `effective_config_version` | Collection / Analysis | provenance event / run metadata | run/config inspector | unknown |
| `effective_config_hash` | Collection / Analysis | provenance event / run metadata | inspector, filter, mixed-version warning | unknown |
| `execution_profile` | Analysis | provenance event / run metadata | record inspector | unknown |
| `context_profile` | Analysis | provenance event / run metadata | inspector, filter, mixed-version warning | unknown |
| `codebook_id` | Analysis | provenance event; `analysis.codebook_refs` fallback | inspector, filter | first codebook ref or unknown |
| `codebook_version` | Analysis | provenance event / run metadata | inspector, filter, mixed-version warning | unknown |
| `codebook_hash` | Analysis | provenance event / run metadata | inspector, filter, mixed-version warning | unknown |
| `model`, `backend`, `task_profile` | Analysis | `analysis.model_runs` and/or provenance | inspector, filters, mixed-version warning | unknown |
| `embedding_model`, `index_version` | Analysis/RAG | provenance event / retrieval metadata | Context/RAG provenance expander | unknown |
| `rag_enabled` | Analysis/RAG | provenance event | filter and record inspector | inferred true only when retrieval IDs exist; otherwise unknown |
| `context_memory_enabled` | Analysis | provenance event | record inspector | inferred true only when context refs exist; otherwise unknown |
| `retrieval_ids` | Analysis/RAG | provenance event / retrieval metadata | Context/RAG provenance expander | empty |
| `context_source_refs` | Analysis/RAG | provenance event; `analysis.memory_refs` fallback | Context/RAG provenance expander | memory refs or empty |
| `previous_summary_id` | Analysis | provenance event / context metadata | Context/RAG provenance expander | unknown |
| `pipeline_version` | Analysis | provenance event / run metadata | inspector, mixed-version warning | unknown |
| `validation_status` | Analysis/review | provenance event or canonical `review.status` | inspector, filter | canonical `review_status` |
| `collection_config_id` | Collection | provenance event | Context/RAG provenance expander | unknown |

The alias resolver in `laclaugpt_visualization.provenance` accepts transitional producer
names such as `config_hash`, `analysis_context_profile`, `machine_profile` and
`collection_provenance_id`, but the UI exposes one stable visualization projection. Producers
should converge on the canonical names above rather than adding Visualization-only names.

## Researcher surfaces

The sidebar can filter by run, context profile, codebook identifier/version/hash, effective
configuration hash, model/backend, validation state, and RAG state. The Researcher Review tab
contains an **Analysis provenance** section and a separate **Context / RAG provenance** drill-
down. The Research Data table adds `prov_*` projections while retaining legacy columns.

When the current view contains more than one recorded value for a material provenance
dimension (run, effective config, context profile, codebook, model/backend/task profile or
pipeline version), the dashboard displays a comparison warning. It does not claim that mixed
runs are invalid; it makes the difference visible so the researcher can decide whether the
comparison is analytically appropriate.

## Safe-display boundary

`safe_provenance_events()` uses an allowlist and drops sensitive/private payload keys. The
researcher UI must never render provenance values containing credentials, API tokens,
connection strings, private prompt bodies, private codebook contents, or researcher notes.
Safe identifiers, versions and hashes are sufficient to answer which configuration produced a
result without copying that configuration into Visualization.

The dashboard may show runtime-private research records supplied by an authorized deployment,
but public code and synthetic fixtures must contain no private study material. Context drill-
down exposes source **references/IDs**, not private source payloads. Full private context remains
in the Analysis/RAG data layer.

## Compatibility

Canonical JSON/JSONL is the reference representation. CSV and SQLite adapters may store
`provenance`, `analysis`, and other nested sections as deterministic JSON strings; the existing
canonical reconstruction layer decodes them before provenance projection. Legacy records with
no provenance continue to load and show their historical fields unchanged.

Synthetic offline tests cover full provenance, missing legacy provenance, mixed versions,
RAG enabled/disabled, human validation state, safe redaction, and JSON/CSV/SQLite loading.
