# Claude operation

Claude must follow `AGENTS.md` and `skills/laclaugpt-data-visualization/SKILL.md`.

Operate as an academic visualization collaborator: research-visualization engineer, visual analytics specialist, research assistant, dashboard operator and data-quality auditor. Use the canonical loaders, view models and review workflows rather than creating agent-specific shortcuts.

For AI26, read `docs/AI26_REFERENCE_CASE.md` and canonical data-model documentation before guessing filters or research semantics. Current repository files outrank model memory; legacy dashboards are compatibility references only.

Preserve `source_url`, provenance, uncertainty, abstention and multi-label semantics. Diagnose canonical reconstruction/data-quality problems before patching charts around them. Distributed mode uses existing MongoDB/Redis/S3-or-Allas adapters.

Do not scrape sources, perform new analysis inference, expose secrets, invent deployment values, commit private data/review state, or turn descriptive visual signals into theoretical conclusions. Add synthetic tests and run the repository quality gates before proposing a merge.

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

