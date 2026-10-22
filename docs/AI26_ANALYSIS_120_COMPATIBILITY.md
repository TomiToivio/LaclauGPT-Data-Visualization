# AI26 Analysis 1.2.0 consumer compatibility (issue #182)

## Scope and version policy

The Visualization schema accepts canonical research-record **1.1.0 and 1.2.0**.
The JSON Schema property layouts are identical in Analysis `main` 1.2.0
and Visualization 1.1.0 at the 2026-10-15 audit. We therefore permit both
versions at the version discriminator only. This is a **reader compatibility**
change, not an upgrade of persisted 1.1.0 records or a reclassification
of research. Future versions must be reviewed and added explicitly.
Do not overwrite `schema_version` while adapting a record.

The canonical adapter reconstructs nested JSON sections, and the researcher's
`raw_record` retains the original canonical payload. Analysis-result
envelopes with a nested `result` are unwrapped without replacing canonical
`provenance` with the transport-level provenance mapping; the latter remains
under `transport_provenance`. Existing legacy EP24 aliases are retained.

Synthetic contract regression:
`tests/test_issue182_analysis_record_contract.py` checks both versions,
evidence pointers, source identity, run_id, model/codebook metadata, provisional
review/history, legacy fields, and optional stages 2/3 (not applicable),
7/8 (experimental). It also rejects unreviewed future version acceptance.

## Scientific interpretation

Stage 6 AI26 research Phase 1 (Paper 1) findings remain provisional until reviewed.
Optional stage 7 DNA and stage 8 SNA are **experimental research Phase 2 (Paper 2)**
interpretations, never research Phase 1 validation. Do not infer discourse or hegemonic status
from graph topology, sentiment, cluster proximity or centrality.
The upstream record's `phase_status` and `experimental_phase_2`
markers must be preserved in the record inspector and graph source payload.
UI capability toggles grant display access only and do not validate outputs.

## MongoDB routing and rollout

Analysis `src/laclaugpt_data_analysis/task_queue.py` writes to
`settings.mongo_database`, collection
`settings.distributed_namespace.mongo_collection("analysis_results")`,
with explicit `project_id` and `run_id`. Visualization
`Settings.expected_mongodb_collection` uses the same distributed namespace,
and configuration validation rejects an explicitly misrouted collection.
For AI26 default namespace this is `ai26__analysis_results`.
Both processes must use the same database and project namespace; public
configuration alone **does not prove** the live Laskin values agree.

Before enabling the deployed consumer, compare the sanitized effective
Analysis Mongo database/project/collection with Visualization health/profile
output. Confirm a bounded synthetic/non-sensitive or approved test record is
visible with exact `source_url`, provenance, review state and stage flags.
Do not adjust production MongoDB collections, start cron or migrate data as
part of this compatibility patch. If the live database differs, fix the
runtime configuration deliberately, not by silently querying every database.

Rollback: revert the schema discriminator to `const: "1.1.0"` and deploy the
previous Visualization build. Existing persisted 1.1.0 records are untouched.
See Analysis #341 for the producer-side staged-pipeline rollout.
