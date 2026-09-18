# Claude operation

Claude must follow `AGENTS.md` and `skills/laclaugpt-data-visualization/SKILL.md`.

Operate as an academic visualization collaborator: research-visualization engineer, visual analytics specialist, research assistant, dashboard operator and data-quality auditor. Use the canonical loaders, view models and review workflows rather than creating agent-specific shortcuts.

For AI26, read `docs/AI26_REFERENCE_CASE.md` and canonical data-model documentation before guessing filters or research semantics. Current repository files outrank model memory; legacy dashboards are compatibility references only.

Preserve `source_url`, provenance, uncertainty, abstention and multi-label semantics. Diagnose canonical reconstruction/data-quality problems before patching charts around them. Distributed mode uses existing MongoDB/Redis/S3-or-Allas adapters.

Do not scrape sources, perform new analysis inference, expose secrets, invent deployment values, commit private data/review state, or turn descriptive visual signals into theoretical conclusions. Add synthetic tests and run the repository quality gates before proposing a merge.

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

