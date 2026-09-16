# LaclauGPT Data Visualization agent skill

Use this skill when an agent operates Visualization. The agent may act as a research-visualization engineer, visual analytics specialist, research assistant, dashboard operator, review-workflow maintainer, and data-quality auditor, while remaining downstream of Collection and Analysis.

## First-read order

Before guessing study semantics or filters, inspect canonical repository material. For AI26 read `docs/AI26_REFERENCE_CASE.md`, then `docs/CANONICAL_DATA_MODEL.md` and any explicitly referenced public codebook/configuration. Canonical current files outrank model memory; legacy dashboards are compatibility/archaeology references only.

## Scope

Pipeline: Collection -> Analysis -> Visualization. Visualization reads canonical analysis records and renders researcher-facing views, supports review workflows and exports, and may inspect data quality relevant to presentation. It does not scrape sources or perform new analysis inference.

Canonical identity is `source_url`. Reconstruct canonical records before dataframe/view transformations; never use MongoDB `_id`, DataFrame row numbers or dashboard-specific IDs as research identity.

## Research-visualization capabilities

Agents may:

- build and repair dashboards, maps, timelines, network views, distributions and comparative views;
- inspect loaders and canonical reconstruction when charts look wrong;
- explain existing analysis outputs without upgrading them into stronger claims;
- support human review, annotations and provenance-aware exports;
- improve accessibility, responsive layout, labels, filtering and discoverability;
- compare alternative visual encodings and document why one is appropriate;
- preserve uncertainty, abstention, multi-label overlap and missing data visibly;
- adapt legacy EP24/other dashboards through boundary adapters without redefining the canonical schema.

Frequency, centrality, layout and co-occurrence are descriptive signals, not automatic evidence of hegemony, antagonism, nodal status or ideological identity.

## AI26

AI26 is the realistic public reference case. Arena is sampling provenance, not ideology. Formation labels are provisional aggregation anchors and may overlap. Candidate signifiers are useful filters/context terms, not validated theoretical conclusions. Never hard-code AI26-specific values into generic contracts when a configurable dimension is appropriate.

## Deployment

Local/laptop workflow may read Analysis files/SQLite directly. Linux web-service workflow may use local or distributed storage. Distributed mode uses MongoDB for queryable canonical records/review state, Redis for project-scoped settings/cache/coordination/pub-sub where useful, and S3-compatible storage such as CSC Allas for referenced artifacts.

Do not run interactive dashboards inside Slurm allocations unless a task explicitly requires a batch-rendering/export job. Do not invent private endpoints, domains, TLS values, CSC project IDs or machine paths.

## Hermes / agent operations

Use `laclaugpt_visualization.integrations.hermes` for effective-config inspection, canonical-input validation, bounded dataset metadata inspection, service validation, summary export, safe cache operations and human-review requests. Do not create a parallel agent-only dashboard or loader stack.

Agent actions should preserve caller/project/execution provenance. Human-review requests use canonical `source_url`.

## Data quality

When a view is surprising, inspect schema version, duplicate identities, missing values, timestamp normalization, location resolution, label uncertainty and backend reconstruction before changing visualization logic. Never silently fill missing research data with invented values.

## Privacy

Never commit research data, researcher review records, credentials, private endpoints, domains, TLS material, CSC project identifiers, machine paths or browser/session data. Keep runtime outputs under private `data/` or external deployment systems. Tests/examples use tiny synthetic fixtures.

## Quality standard

Keep loaders, reconstruction, transforms, review persistence and page orchestration separate. Add synthetic tests for substantial behavior changes and run the repository public-tree/lint/test gates before proposing a merge.