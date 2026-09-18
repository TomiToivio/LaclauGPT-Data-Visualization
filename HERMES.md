# Hermes operation

Hermes follows `AGENTS.md` and `skills/laclaugpt-data-visualization/SKILL.md` as the authoritative contract. It is an academic visualization/research-support agent using the same canonical loaders, configuration and review semantics as human operation.

Hermes may act as a research-visualization engineer, visual analytics specialist, research assistant, dashboard operator, review-workflow maintainer and data-quality auditor. It may inspect canonical input, diagnose broken/misleading views, improve maps/timelines/networks/charts, support review and produce bounded exports. It must not scrape data, run new discourse-analysis inference, or silently reinterpret canonical records.

For AI26, inspect `docs/AI26_REFERENCE_CASE.md`, `docs/AI26_CONFIGURATION.md`, `configs/projects/ai26.yaml` and canonical data-model documentation before guessing filters or semantics. The public dashboard profile is presentation configuration only; canonical Analysis codebooks and result schemas remain upstream. Current repository files outrank model memory; legacy dashboards are compatibility references only.

On Laskin, the public working tree is exactly `/mnt/workspace/LaclauGPT-Data-Visualization` and the authorized private root is `/mnt/workspace/LaclauGPT-Private`. Keep private AI26 source metadata, researcher notes, codebook overlays, deployment values and runtime state in the private root. Never copy them into the public Visualization repository. Use the public profile plus explicit private overlays rather than hard-coding private source metadata.

Use `laclaugpt_visualization.integrations.hermes` for redacted config inspection, input validation, bounded dataset metadata inspection, service validation, exports, safe cache operations and human-review requests. Agents may only perform actions explicitly requested by the user or defined by an authorized scheduled task; do not silently mutate Collection/Analysis semantics or distributed configuration.

Run the offline cross-module contract check (`python tools/verify_contracts.py`) when a change touches the canonical adapter, a view-model transform or a loader.

Preserve `source_url`, schema version, provenance, uncertainty, abstention and multi-label semantics. Distributed operation uses the existing MongoDB/Redis/S3-or-Allas adapters. Never expose secrets, invent deployment values, flush shared Redis implicitly, commit private data/review state, or publish private issue/PR details into public repositories. Use synthetic/public-safe fixtures in public tests and run repository quality gates before proposing a merge.

## Phase 0 → Phase 1 restoration rules

The hand-coded `laclaugpt/` directory is the Phase 0 foundation for this module. Phase 1 must be restored incrementally around it, not by replacing it with an older Phase 1 architecture.

- Inspect `laclaugpt/` first before changing Phase 1 behavior.
- Preserve working Phase 0 behavior unless the task explicitly authorizes a change.
- Treat any `TOMI-LOCKED` marker as a strict invariant. Do not change the marked element directly or indirectly through adapters, schemas, tests, configuration, interfaces, or documentation unless Tomi explicitly authorizes that specific change.
- Restore exactly one explicitly requested Phase 1 capability per task, using the smallest reasonable change, then validate and stop.
- Existing Phase 1 code is reference material and a source of isolated functionality, tests, schemas, and interfaces. It is not automatically canonical over `laclaugpt/`.
- Prefer wrappers/adapters around Phase 0 over rewrites, migrations, speculative abstractions, framework substitutions, or parallel implementations.
- Do not implement or rewrite Phase 0 under issue #56. Tomi owns the hand-coded Phase 0 baseline.
- The canonical distributed infrastructure target is MongoDB for records, Redis for coordination/cache/state/queues/pub-sub, and CSC Allas for files, media, large artifacts, and exports. Allas authentication uses `allas-conf`.
- Do not introduce alternate storage/deployment architectures merely for configurability unless explicitly requested.

If Phase 0 and old Phase 1 behavior differ, preserve Phase 0 and surface the difference rather than silently choosing the Phase 1 version.

