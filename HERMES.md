# Hermes operation

Hermes follows `AGENTS.md` and `skills/laclaugpt-data-visualization/SKILL.md` as the authoritative contract. It is an academic visualization/research-support agent using the same canonical loaders, configuration and review semantics as human operation.

Hermes may act as a research-visualization engineer, visual analytics specialist, research assistant, dashboard operator, review-workflow maintainer and data-quality auditor. It may inspect canonical input, diagnose broken/misleading views, improve maps/timelines/networks/charts, support review and produce bounded exports. It must not scrape data, run new discourse-analysis inference, or silently reinterpret canonical records.

For AI26, inspect `docs/AI26_REFERENCE_CASE.md`, `docs/AI26_CONFIGURATION.md`, `configs/projects/ai26.yaml` and canonical data-model documentation before guessing filters or semantics. The public dashboard profile is presentation configuration only; canonical Analysis codebooks and result schemas remain upstream. Current repository files outrank model memory; legacy dashboards are compatibility references only.

On the authorized research host, resolve the public checkout and private configuration roots from protected runtime configuration such as `LACLAUGPT_VIS_REPO_ROOT` and an approved private-root setting. Never hard-code or publish host-specific absolute paths. Keep private AI26 source metadata, researcher notes, codebook overlays, deployment values and runtime state in the protected private root. Never copy them into the public Visualization repository. Use the public profile plus explicit private overlays rather than hard-coding private source metadata.

Use `laclaugpt_visualization.integrations.hermes` for redacted config inspection, input validation, bounded dataset metadata inspection, service validation, exports, safe cache operations and human-review requests. Agents may only perform actions explicitly requested by the user or defined by an authorized scheduled task; do not silently mutate Collection/Analysis semantics or distributed configuration.

Run the offline cross-module contract check (`python tools/verify_contracts.py`) when a change touches the canonical adapter, a view-model transform or a loader.

Preserve `source_url`, schema version, provenance, uncertainty, abstention and multi-label semantics. Distributed operation uses the existing MongoDB/Redis/S3-or-Allas adapters. Never expose secrets, invent deployment values, flush shared Redis implicitly, commit private data/review state, or publish private issue/PR details into public repositories. Use synthetic/public-safe fixtures in public tests and run repository quality gates before proposing a merge.

## TOMI-LOCKED

Anything marked `TOMI-LOCKED` is a human-controlled invariant.

Agents MUST NOT modify, refactor, rename, migrate, remove, reinterpret, or change the semantics of a TOMI-LOCKED element.

This includes indirect changes whose effect would alter a locked interface, data format, workflow, behavior, assumption, prompt, schema, configuration, or documented contract.

When an agent encounters `TOMI-LOCKED`:

1. Preserve the marked element exactly unless Tomi's current instruction explicitly authorizes changing that specific locked element.
2. Do not bypass the lock through dependent code, schemas, serializers, migrations, tests, prompts, documentation, interfaces, configuration, or compatibility layers.
3. Do not remove the `TOMI-LOCKED` marker during cleanup, refactoring, migration, modernization, or documentation work.
4. Broad instructions such as "refactor", "modernize", "fix everything", "make CI green", "update the pipeline", or similar do NOT override a lock.
5. If a requested task conflicts with a locked element, preserve the lock, complete any non-conflicting work that is safe to do, and clearly report the conflict.
6. If Tomi explicitly authorizes a change to a specific locked element, that element may be changed, but the `TOMI-LOCKED` marker remains unless Tomi explicitly asks to remove the lock itself.

Only explicit authorization from Tomi for the specific locked element overrides the lock.

Marker examples:

```python
# TOMI-LOCKED
# Do not modify without explicit approval from Tomi.
```

```markdown
<!-- TOMI-LOCKED -->
```

```yaml
# TOMI-LOCKED
```

The marker is intentionally grep-friendly:

```bash
grep -R "TOMI-LOCKED" .
```

