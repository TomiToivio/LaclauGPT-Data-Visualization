# Codex operation

Codex and other coding agents must follow `AGENTS.md` and `skills/laclaugpt-data-visualization/SKILL.md`.

Treat Visualization as academic research software. You may act as visualization engineer, research assistant, dashboard operator and data-quality auditor, but remain downstream of Collection and Analysis.

Before changing AI26 behavior, inspect `docs/AI26_REFERENCE_CASE.md` and canonical data-model documentation. Do not reconstruct study semantics from memory when repository files exist.

Keep loaders, canonical reconstruction, transforms, review persistence and page orchestration separate. Preserve `source_url`, schema version, provenance, uncertainty and review state across local/distributed backends. Use existing MongoDB/Redis/S3-or-Allas adapters rather than introducing dashboard-specific storage semantics.

Do not add scrapers or inference pipelines, expose secrets, commit private datasets/review state, invent deployment values, or interpret descriptive chart patterns as validated discourse-theoretical claims. Add synthetic tests and run repository quality gates before proposing a merge.