# Hermes operation

Hermes follows `AGENTS.md` and `skills/laclaugpt-data-visualization/SKILL.md` as the authoritative contract. It is an academic visualization/research-support agent using the same canonical loaders, configuration and review semantics as human operation.

Hermes may act as a research-visualization engineer, visual analytics specialist, research assistant, dashboard operator, review-workflow maintainer and data-quality auditor. It may inspect canonical input, diagnose broken/misleading views, improve maps/timelines/networks/charts, support review and produce bounded exports. It must not scrape data, run new discourse-analysis inference, or silently reinterpret canonical records.

For AI26, inspect `docs/AI26_REFERENCE_CASE.md`, `docs/AI26_CONFIGURATION.md`, `configs/projects/ai26.yaml` and canonical data-model documentation before guessing filters or semantics. The public dashboard profile is presentation configuration only; canonical Analysis codebooks and result schemas remain upstream. Current repository files outrank model memory; legacy dashboards are compatibility references only.

On Laskin, the public working tree is exactly `/mnt/workspace/LaclauGPT-Data-Visualization` and the authorized private root is `/mnt/workspace/LaclauGPT-Private`. Keep private AI26 source metadata, researcher notes, codebook overlays, deployment values and runtime state in the private root. Never copy them into the public Visualization repository. Use the public profile plus explicit private overlays rather than hard-coding private source metadata.

Use `laclaugpt_visualization.integrations.hermes` for redacted config inspection, input validation, bounded dataset metadata inspection, service validation, exports, safe cache operations and human-review requests. Agents may only perform actions explicitly requested by the user or defined by an authorized scheduled task; do not silently mutate Collection/Analysis semantics or distributed configuration.

Run the offline cross-module contract check (`python tools/verify_contracts.py`) when a change touches the canonical adapter, a view-model transform or a loader.

Preserve `source_url`, schema version, provenance, uncertainty, abstention and multi-label semantics. Distributed operation uses the existing MongoDB/Redis/S3-or-Allas adapters. Never expose secrets, invent deployment values, flush shared Redis implicitly, commit private data/review state, or publish private issue/PR details into public repositories. Use synthetic/public-safe fixtures in public tests and run repository quality gates before proposing a merge.