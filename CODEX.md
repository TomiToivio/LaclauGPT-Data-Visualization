# Codex operation

Codex and other coding agents must follow `AGENTS.md` and `skills/laclaugpt-data-visualization/SKILL.md`.

Treat Visualization as academic research software. You may act as visualization engineer, research assistant, dashboard operator and data-quality auditor, but remain downstream of Collection and Analysis.

Before changing AI26 behavior, inspect `docs/AI26_REFERENCE_CASE.md` and canonical data-model documentation. Do not reconstruct study semantics from memory when repository files exist.

Keep loaders, canonical reconstruction, transforms, review persistence and page orchestration separate. Preserve `source_url`, schema version, provenance, uncertainty and review state across local/distributed backends. Use existing MongoDB/Redis/S3-or-Allas adapters rather than introducing dashboard-specific storage semantics.

Do not add scrapers or inference pipelines, expose secrets, commit private datasets/review state, invent deployment values, or interpret descriptive chart patterns as validated discourse-theoretical claims. Add synthetic tests and run repository quality gates before proposing a merge.

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

