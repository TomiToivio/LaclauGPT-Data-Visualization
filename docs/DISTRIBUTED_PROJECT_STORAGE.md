# Distributed project storage

Visualization implements the same multi-project namespace as Collection and Analysis. The machine-readable contract is `schemas/distributed-project.schema.json`.

Set `LACLAUGPT_VIS_PROJECT_ID` to a stable project ID such as `ai26`, `ep24`, `brazil26` or `hungary26`.

## Redis control plane

Visualization can use the shared Redis namespace for project manifests, visualization settings, cache state and review/update streams:

```text
laclaugpt:<project>:manifest:current
laclaugpt:<project>:settings:visualization:current
laclaugpt:<project>:stream:analyzed
laclaugpt:<project>:stream:review-events
laclaugpt:<project>:worker:visualization:<worker_id>
laclaugpt:<project>:cache:<name>
```

Redis documents are small, versioned and hash-verifiable. Large datasets and files are referenced rather than embedded. Secrets never belong in the shared control documents.

## MongoDB

When `data_backend=mongodb`, Visualization reads the canonical Analysis -> Visualization handoff collection derived from the project ID:

```text
ai26__analysis_results
ep24__analysis_results
brazil26__analysis_results
hungary26__analysis_results
```

This is the same collection populated by Analysis for the `laclaugpt-analysis-visualization-v1` handoff. Queries also include `project_id` as a second isolation guard. An explicit `mongodb_collection` override is retained as a configuration field for compatibility, but readiness fails when it diverges from the canonical `<project>__analysis_results` source so a deployment cannot start healthy while reading an unrelated or empty collection.

Embedded relations in canonical analysis results are the portable graph baseline. The optional `<project>__relations` collection remains available only for bounded graph traversal deployments that publish a separate relation index; normal Monitor/Review/Explore views do not require it.

Review stores may use the parallel `<project>__reviews` collection when a shared MongoDB review backend is enabled.

## S3 / CSC Allas

S3/Allas downloads are rooted under the configured project prefix:

```text
projects/<project>/media/
projects/<project>/transcripts/
projects/<project>/frames/
projects/<project>/analysis/
projects/<project>/exports/
```

This lets one Pouta visualization service or multiple project-specific services share a bucket while retaining deterministic isolation.

## Switching projects

Project selection is deployment configuration, not a dashboard filter. A running worker/dashboard should use exactly one `project_id`; switching projects means starting a separately configured process or restarting with a different project ID. This prevents a UI filter mistake from becoming a cross-project data leak.
