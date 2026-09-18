# Phase 0 foundation and incremental Phase 1 restoration

Repository doctrine for Visualization.

The Phase 0 visualization baseline lives under `laclaugpt/`. It is intentionally small and hand-readable, but it may be implemented and maintained by agents when Tomi requests it. There is no reservation requiring Tomi to build it manually.

## Treat `laclaugpt/` as the foundation

- Inspect `laclaugpt/` before making Phase 0 or Phase 1 changes.
- Keep the Phase 0 core simple and directly runnable.
- Do not replace it wholesale with a framework, orchestration layer or plugin system.
- Prefer small changes with focused tests.
- Existing Phase 1 code outside `laclaugpt/` is a reference/source, not automatically the architecture of the Phase 0 baseline.

## Phase 0 runtime

Phase 0 Visualization is downstream of the RSS-only Analysis baseline. It reads analysis results directly from MongoDB and provides simple list, inspect and export operations.

Phase 0 deliberately does not require Redis, CSC Allas/S3, multimodal assets, DNA, SNA, graph infrastructure or distributed orchestration.

See `PHASE0_VISUALIZATION_COMPATIBILITY.md` for the concrete data contract.

## Restore Phase 1 incrementally

After the Phase 0 path works, restore richer capabilities one explicit feature at a time. Preserve working Phase 0 behavior, avoid unrelated refactors, validate each step, and stop after the requested capability is complete.

## TOMI-LOCKED

Anything marked `TOMI-LOCKED` remains a human-controlled invariant. Agents must not change a locked element unless Tomi explicitly authorizes changing that specific element.


See `docs/PHASE0_VISUALIZATION.md` for the thin Phase 0 visualization compatibility layer: the MongoDB analysis inputs it reads and the minimal display/export path.

## Status

`laclaugpt/` now contains the minimal Phase 0 visualization implementation. It is expected to evolve through small, tested Phase 0 changes before Phase 1 capabilities are restored around it.
