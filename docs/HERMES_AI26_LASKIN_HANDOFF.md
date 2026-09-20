# Hermes handoff: AI26 Phase 1 Visualization on Laskin

This is the host-execution handoff for issue #136. The unified AI26 Phase 1 dashboard and Laskin deployment artifacts are already implemented. Hermes should verify and operate them on Laskin, not fork an AI26-specific visualization stack.

## Already prepared in Git

- AI26 project selection and canonical dashboard entry point.
- Monitor / Researcher Review / Explore plus optional upstream network views.
- MongoDB-backed canonical data path, Redis optional control/status path, Allas/S3 references.
- Graceful states for pending/unanalysed data and unavailable optional capabilities.
- `deploy/preflight-laskin-ai26.sh` sanitized preflight.
- `deploy/laclaugpt-visualization-laskin-ai26.service.example` service template.
- `docs/AI26_LASKIN_DASHBOARD.md` deployment, health, recovery and legacy-service retirement runbook.
- Synthetic regression coverage for AI26 selection, mixed analyzed/pending state and study isolation.

Visualization must not perform discourse inference or synthesize missing theoretical relations.

## Hermes mission on Laskin

1. Read `AGENTS.md`, `HERMES.md`, `docs/AI26_LASKIN_DASHBOARD.md`, issue #136 and the AI26 project config before changes.
2. Verify the exact public checkout and authorized private environment. Do not copy private endpoints, credentials, notes, codebooks or row-level data into Git or public issue comments.
3. Update/install:

```bash
cd /mnt/workspace/LaclauGPT-Data-Visualization
git status --short
git pull --ff-only
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[remote,dev]'
```

4. Run repository gates:

```bash
python scripts/check_public_tree.py
ruff check .
pytest
npm run test:legacy
```

5. Retire the documented legacy AI26 dashboard/export user units if present. Do not re-enable the old JSONL export path.
6. Run the sanitized Laskin preflight:

```bash
bash deploy/preflight-laskin-ai26.sh
```

7. Verify the effective profile reports `project_id=ai26`, canonical browser/data contract, distributed/MongoDB data access, expected Redis capabilities and a conservative private bind.
8. Start the production-equivalent dashboard only after preflight passes, using the documented service template or manual `laclaugpt-visualize serve` path.
9. Verify with current/synthetic-safe data:
   - Monitor shows corpus size, analyzed versus awaiting-analysis state and latest timestamps;
   - Researcher Review preserves stable `source_url`, evidence, provenance, structured result, uncertainty/abstention and human review state;
   - Explore renders available timelines/distributions;
   - graph/SNA views appear only when explicit upstream products exist;
   - new Analysis results appear without code changes or manual conversion;
   - awaiting-analysis, malformed/rejected, stale, empty-filter and unavailable-optional-service states do not crash;
   - AI26 cannot bleed into Brazil26 or another project namespace.
10. Restart the service and verify durable state is unchanged.
11. Verify the service remains private-network/loopback bound unless an already-authorized protected access layer requires otherwise.

## Cross-repo entrance check

Use the canonical Analysis output contract directly. No visualization-side adapter may reinterpret AI26 semantics. Confirm a fresh synthetic/public-safe result from the Analysis Laskin worker appears in Monitor, Researcher Review and Explore without a hand-written conversion step.

The handoff schema expected from Analysis is `laclaugpt-analysis-visualization-v1`; preserve upstream schema version, `source_url`, evidence and provenance.

## When to change code

Only change public code if Laskin reveals a reproducible generic defect. Add a synthetic regression test, keep remote services lazy for public CI, and do not move Analysis logic into Visualization.

## Completion evidence for issue #136

Post only sanitized evidence: commit SHA, test/preflight result, service health, project id, bounded corpus/analyzed counts, restart result, legacy-unit retirement state, and confirmation that a fresh Analysis result became visible unchanged. Never post private endpoints, credentials, research rows or sensitive provenance paths.
