# LaclauGPT Data Visualization agent skill

Operate Visualization as the downstream view layer of the LaclauGPT pipeline.

## Scope

Pipeline: Collection -> Analysis -> Visualization. Visualization reads canonical analysis records and renders researcher-facing views. It does not scrape sources or perform analysis inference.

Canonical identity is `source_url`. Reconstruct canonical records before dataframe/view transformations; never use MongoDB `_id` as research identity.

## Laptop workflow

Use `machine=laptop`, `execution=cli`, `storage=local`, `cache=memory`. Read a configured Analysis data root directly when both modules share a machine. CSV/JSONL/Pandas-compatible files and SQLite are supported. Runtime state belongs under private `data/`.

## Linux web-service workflow

Use `machine=linux-server`, `execution=web-service`. Storage may still be local, or it may be distributed. Check `laclaugpt-visualize health` before service start. Do not run the interactive dashboard inside Slurm/Roihu allocations.

## Distributed workflow

MongoDB stores queryable canonical records/review state; Redis provides project-scoped settings, cache, coordination and messaging; S3-compatible storage such as CSC Allas stores large files/artifacts. CSV/JSONL is the manual cross-machine fallback.

## Hermes operations

Use `laclaugpt_visualization.integrations.hermes` for effective-config inspection, canonical-input validation, dataset metadata inspection, service validation, summary export, safe cache clearing and human-review requests. Do not create a parallel agent-only dashboard.

Agent-triggered actions should use caller `hermes-agent` and preserve project/execution provenance. Human-review requests must use canonical `source_url`.

## Privacy

Never commit research data, researcher review records, credentials, private endpoints, domains, TLS material, CSC project identifiers, machine paths, or browser/session data. Keep runtime outputs in private `data/` or external secret/deployment management.
