# Hand-coded baseline and incremental implementation

Repository doctrine for Visualization (issue #56). This records the rules for
building the current pipeline **around** the hand-coded baseline in `laclaugpt/`.
It defines implementation rules only; the baseline itself is not implemented by
this document.

The hand-coded visualization baseline lives under `laclaugpt/`. Tomi builds
and finishes it manually. It is the **foundation** around which further
visualization functionality is added incrementally — not a first draft to be replaced.

## Treat `laclaugpt/` as the foundation

- Agents MUST inspect `laclaugpt/` before changing visualization behaviour.
- Do not replace the hand-coded baseline wholesale with a new abstraction, framework,
  orchestration layer, plugin architecture, or agent-generated redesign.
- Do not move functionality out of `laclaugpt/` merely to match the older modular
  package layout.
- Prefer adapters and wrappers around the baseline over rewrites.
- Preserve working baseline behaviour unless the task explicitly says otherwise.

## The earlier modular code is a source, not the architecture

Code outside `laclaugpt/` (the earlier modular package) remains useful as:

- a reference implementation;
- a source of tests;
- a source of schemas and interfaces;
- a source of isolated functionality to adapt.

It is **not** automatically authoritative over the hand-coded `laclaugpt/`
implementation. When the baseline and the earlier modular code differ, agents must not
silently choose the modular version. Preserve the baseline and surface the difference
unless the task explicitly instructs otherwise.

## Add one capability at a time

1. Inspect `laclaugpt/` first.
2. Identify exactly **one** capability to add.
3. Add that capability around the baseline implementation with the smallest
   possible change.
4. Preserve existing baseline behaviour unless the task explicitly says otherwise.
5. Run the tests/validation for that one step.
6. Stop.
7. Continue with the next capability only in a separate, explicitly requested task.

Do not attempt a "big bang" rewrite. Do not combine multiple
architectural changes into one change unless Tomi explicitly asks.

```
hand-coded baseline in laclaugpt/   (legacy core)
        ↓
one small capability added to the current pipeline
        ↓
validation
        ↓
next addition
```

Agents working on incremental implementation MUST also:

- preserve TOMI-LOCKED elements exactly (see below);
- avoid unrelated refactors;
- avoid speculative abstraction;
- avoid large migrations;
- avoid replacing hand-coded baseline logic with framework-driven equivalents unless
  explicitly requested;
- keep changes small enough to review and reason about;
- stop after the requested step is complete.

Broad requests such as "continue the implementation", "modernize", "refactor",
"clean up" or "make the architecture nicer" are **not** authorization to rewrite the
`laclaugpt/` core.

## Distributed architecture defaults

Assume the main deployment/runtime model is distributed:

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

## Status

`laclaugpt/` does not exist in this repository yet; Tomi creates it manually.
Incremental implementation begins only after Tomi explicitly requests the first
step. No baseline code is implemented by this document.
