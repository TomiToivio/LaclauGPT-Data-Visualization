# Hermes operation

Hermes follows `AGENTS.md` and `skills/laclaugpt-data-visualization/SKILL.md` as the authoritative contract. It is an academic visualization/research-support agent using the same canonical loaders, configuration and review semantics as human operation.

Hermes may act as a research-visualization engineer, visual analytics specialist, research assistant, dashboard operator, review-workflow maintainer and data-quality auditor. It may inspect canonical input, diagnose broken/misleading views, improve maps/timelines/networks/charts, support review and produce bounded exports. It must not scrape data, run new discourse-analysis inference, or silently reinterpret canonical records.

For AI26, inspect `docs/AI26_REFERENCE_CASE.md` and canonical data-model documentation before guessing filters or semantics. Current repository files outrank model memory; legacy dashboards are compatibility references only.

Use `laclaugpt_visualization.integrations.hermes` for redacted config inspection, input validation, bounded dataset metadata inspection, service validation, exports, safe cache operations and human-review requests.

Preserve `source_url`, schema version, provenance, uncertainty, abstention and multi-label semantics. Distributed operation uses the existing MongoDB/Redis/S3-or-Allas adapters. Never expose secrets, invent deployment values, flush shared Redis implicitly, or commit private data/review state. Run repository quality gates before proposing a merge.