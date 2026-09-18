# Phase 0 foundation and incremental Phase 1 restoration

Repository doctrine for Visualization (issue #56). This records the rules for
rebuilding Phase 1 **around** the hand-coded Phase 0 baseline. It defines
restoration rules only; it does not implement Phase 0.

The hand-coded Phase 0 visualization baseline lives under `laclaugpt/`. Tomi builds
and finishes it manually. It is the **foundation** around which Phase 1
functionality is restored — not a first draft to be replaced.

## Treat `laclaugpt/` as the foundation

- Agents MUST inspect `laclaugpt/` before making Phase 1 changes.
- Do not replace Phase 0 wholesale with a new abstraction, framework,
  orchestration layer, plugin architecture, or agent-generated redesign.
- Do not move functionality out of `laclaugpt/` merely to match the older Phase 1
  layout.
- Prefer adapters and wrappers around Phase 0 over rewrites.
- Preserve working Phase 0 behavior unless the task explicitly says otherwise.

## Existing Phase 1 code is a source, not the architecture

Phase 1 code outside `laclaugpt/` remains useful as:

- a reference implementation;
- a source of tests;
- a source of schemas and interfaces;
- a source of isolated functionality to restore.

It is **not** automatically authoritative over the hand-coded Phase 0
implementation. When Phase 0 and older Phase 1 code differ, agents must not
silently choose the Phase 1 version. Preserve Phase 0 and surface the difference
unless the task explicitly instructs otherwise.

## Restore one capability at a time

1. Inspect `laclaugpt/` first.
2. Identify exactly **one** Phase 1 capability to restore.
3. Add that capability around the Phase 0 implementation with the smallest
   possible change.
4. Preserve existing Phase 0 behavior unless the task explicitly says otherwise.
5. Run the tests/validation for that one step.
6. Stop.
7. Continue with the next capability only in a separate, explicitly requested task.

Do not attempt a "big bang" restoration of Phase 1. Do not combine multiple
architectural restorations into one change unless Tomi explicitly asks.

```
Phase 0 legacy core in laclaugpt/
        ↓
small Phase 1 addition
        ↓
validation
        ↓
next Phase 1 addition
```

Agents working on Phase 1 restoration MUST also:

- preserve TOMI-LOCKED elements exactly (see below);
- avoid unrelated refactors;
- avoid speculative abstraction;
- avoid large migrations;
- avoid replacing hand-coded Phase 0 logic with framework-driven equivalents unless
  explicitly requested;
- keep changes small enough to review and reason about;
- stop after the requested restoration step is complete.

Broad requests such as "continue Phase 1", "modernize", "refactor", "clean up" or
"make the architecture nicer" are **not** authorization to rewrite the Phase 0 core.

## Distributed architecture defaults

From this point forward, assume the main deployment/runtime model is distributed:

- **MongoDB** for records and document persistence;
- **Redis** for coordination, cache, state, queues, pub/sub and lightweight
  runtime coordination;
- **S3-compatible object storage such as CSC Allas** for files, media, large
  artifacts and exports. CSC Allas authentication uses `allas-conf`.

Do not spend effort maintaining or inventing multiple alternate storage/deployment
modes unless Tomi explicitly requests them. In particular, do not add new
local-only, SQLite-first, filesystem-only, alternate-object-store, alternate-queue
or alternate-database architectures merely for configurability.

Local development may still use the same interfaces where necessary, but the
canonical architecture targets MongoDB + Redis + CSC Allas.

## TOMI-LOCKED

Anything marked `TOMI-LOCKED` is a human-controlled invariant.

Agents MUST NOT modify, refactor, rename, migrate, remove, reinterpret, or change
the semantics of a TOMI-LOCKED element. This includes indirect changes whose effect
would alter a locked interface, data format, workflow, behavior, assumption,
schema, configuration or documented contract.

When an agent encounters `TOMI-LOCKED`:

1. Preserve the marked element exactly unless Tomi's current instruction explicitly
   authorizes changing that specific locked element.
2. Do not bypass the lock through dependent code, schemas, serializers, migrations,
   tests, documentation, interfaces, configuration or compatibility layers.
3. Do not remove the `TOMI-LOCKED` marker during cleanup, refactoring, migration,
   modernization or documentation work.
4. Broad instructions such as "refactor", "modernize", "clean up" or "make CI
   green" do NOT override a lock.
5. If a requested task conflicts with a locked element, preserve the lock, complete
   any non-conflicting work that is safe to do, and clearly report the conflict.
6. If Tomi explicitly authorizes a change to a specific locked element, that
   element may be changed, but the `TOMI-LOCKED` marker remains unless Tomi
   explicitly asks to remove the lock itself.

Only explicit authorization from Tomi for the specific locked element overrides the
lock. The marker is intentionally grep-friendly:

```bash
grep -R "TOMI-LOCKED" .
```

<<<<<<< HEAD

See `docs/PHASE0_VISUALIZATION.md` for the thin Phase 0 visualization compatibility layer: the MongoDB analysis inputs it reads and the minimal display/export path.

=======
>>>>>>> 4c14fa6db4ff0845a48c7ddeb2c3f9e200982565
## Status

`laclaugpt/` does not exist in this repository yet; Tomi creates it manually.
Phase 1 restoration begins only after Tomi explicitly requests the first
restoration step. No Phase 0 code is implemented by this document.
