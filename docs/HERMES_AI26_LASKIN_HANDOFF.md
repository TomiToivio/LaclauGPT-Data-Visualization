# Hermes handoff: AI26 Phase 1 Visualization on Laskin (issue #161)

This is the host-execution handoff for [Visualization #161](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/issues/161), Step 3 of Collection → Analysis → Visualization. This document is an execution checklist, **not** a certificate of a live run. The current unified dashboard and deployment artifacts are already implemented; do not create a separate AI26-specific dashboard or conversion layer.

## Entrance gates and current evidence

- [Collection #169](https://github.com/TomiToivio/LaclauGPT-Data-Collection/issues/169) records **STEP 1 PASS** from a live Laskin run. Its final sanitized run reported canonical schema `1.1.0`, handoff `ai26-phase1-handoff-v1`, stable identity and no namespace contamination.
- [Analysis #294](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/issues/294) records **STEP 2 PASS** after fixes #295 and #296. Its completion evidence reports fresh, durable Analysis results, preserved evidence/provenance and the `laclaugpt-analysis-visualization-v1` handoff accepted by Visualization's loader without conversion. #299 is a closed robustness follow-up.
- Those reports establish the upstream gates, **not** a live Visualization service/restart/canary certificate. Reconfirm the fresh result and source identity from the authorized private runtime before Step 3. Never substitute an old synthetic result for the full-chain canary.

## Mandatory reading and invariants

Read `AGENTS.md`, `HERMES.md`, `skills/laclaugpt-data-visualization/SKILL.md`, `docs/AI26_REFERENCE_CASE.md`, `docs/AI26_CONFIGURATION.md`, `configs/projects/ai26.yaml`, `docs/AI26_DASHBOARD.md`, `docs/AI26_LASKIN_DASHBOARD.md`, `docs/DEPLOYMENT_PROFILES.md`, the canonical loader/result-envelope documentation and issue #161. Repository files and authorized private runtime configuration outrank model memory. Preserve every `TOMI-LOCKED` invariant.

Phase 1 work and service execution use `main`, not the passive `phase-1` mirror. Use the existing Laskin checkout and protected environment, checking `git status --short` before `git pull --ff-only origin main`; do not discard unrelated work. Keep actual host paths, credentials, endpoints, source/target metadata, row-level data, source text/media, provenance paths and researcher annotations out of public Git and issue comments.

Visualization consumes canonical Analysis output, reconstructs and validates records, presents Monitor/Explore/Review/Reports and supports human review. It does not scrape, perform discourse inference, invent absent relations or network edges, or promote machine output to human-validated interpretation. `source_url` remains the research identity; missing evidence, uncertainty, abstention and pending/error states must not be silently erased.

## Laskin execution order

1. **Checkout and offline gates.** Record executed `main` SHA. Install through the documented `.[remote,dev]` path. Run `python scripts/check_public_tree.py`, `.venv/bin/ruff check .`, `.venv/bin/pytest`, `npm run test:legacy`, and `python tools/verify_contracts.py`. Report any failures separately from host/runtime failures.
2. **Redacted configuration.** Use the canonical Settings/Hermes integration, without printing private values. Confirm `project_id=ai26`, `browser_data_contract=canonical`, `machine=linux-server`, `execution=web-service`, selected MongoDB/Redis/S3 capabilities, private output paths and a safe loopback/protected bind. Verify private `EnvironmentFile` agrees with the service template. The application compatibility default remains `phase0`; do not rely on it for AI26.
3. **Upstream entrance.** Find one *fresh* Collection #169 → Analysis #294 result in the shared `ai26` namespace. Validate `laclaugpt-analysis-visualization-v1` (where still current), canonical schema version, `source_url`, source evidence, analysis provenance, uncertainty/abstention, provisional review state and pending/rejected distinctions. No manual JSON reshaping, export shim or semantic conversion. If this fails, update the owning Analysis issue and mark Step 3 blocked.
4. **Preflight and service.** Retire obsolete AI26 dashboard/export units as documented; do not revive the old JSONL exporter. Run `bash deploy/preflight-laskin-ai26.sh` with the authorized private environment. Do not bypass failure. Then start the canonical service via the documented systemd template or `laclaugpt-visualize serve`. Verify profile, health and service manager state, without publishing sensitive logs.
5. **Monitor and Review.** Compare sanitized corpus/analyzed/pending counts with the backend. Verify timestamps and source activity. Inspect a bounded sample in Researcher Review for unchanged `source_url`, evidence, result, model/config provenance, uncertainty, abstention and review state. Exercise supported accept/reject/revise/annotate operations only on authorized test/review records; merely viewing a result is not human validation. Check drill-down to evidence where claimed.
6. **Explore and conditional networks.** Verify valid timelines, distributions, filters and absent-versus-zero treatment. Graph/network views must appear only for explicit upstream products; no inferred relation may be synthesized in Visualization.
7. **Adverse states and isolation.** Exercise pending, malformed/rejected, empty, stale, empty-filter, partial/abstention-heavy and unavailable optional Redis/graph/object-reference states without crashing unrelated views or showing false success. Verify project-scoped queries, cache, review state, reports, exports and status streams do not mix AI26 with Brazil26/other studies.
8. **Fresh full-chain canary.** Trace at least one fresh record through Collection #169 → Analysis #294 → Visualization by a sanitized stable identifier. Confirm visible unchanged evidence/provenance/uncertainty/review state without code changes or conversion.
9. **Restart and durability.** Restart by the documented service-manager path. Confirm healthy recovery, unchanged canonical data and durable review state, safe cache rebuild, no duplicates and no Analysis rerun triggered by Visualization restart.

## Defects and stop rule

Search open and recently closed issues before filing each concrete reproducible defect. Update the existing owning issue when appropriate; otherwise file a narrowly scoped issue in Collection, Analysis or Visualization as appropriate, with sanitized reproduction, affected SHA/component, severity, impact, next diagnostic step and acceptance criteria. Continue through clearly documented non-blocking display defects. Stop certification for lost evidence/provenance/uncertainty, cross-project leakage, wrong-record review mutations, unsafe exposure, data corruption after restart, manual semantic conversion, new Visualization inference, or a `TOMI-LOCKED` bypass.

## Sanitized completion record for #161

Post execution date/time and Visualization SHA; Collection #169 and Analysis #294 status/SHAs; project/schema/envelope; quality gates; preflight and service health; bounded corpus/analyzed/pending counts; Monitor, Review, Explore and conditional graph status; degraded-state and isolation results; fresh full-chain canary; restart/durability; and defect links. End with **STEP 3 PASS / FULL CHAIN PASS** only if every required gate actually passed on Laskin, otherwise **STEP 3 BLOCKED / FULL CHAIN BLOCKED** with the specific missing proof or reproducible blocker.

A successful technical canary is not equivalent to completing the paper's scientific human-validation sample.
