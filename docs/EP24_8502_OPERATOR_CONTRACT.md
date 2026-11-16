# EP24 :8502 researcher dashboard: agent operating contract

> **Scope:** maintenance of an existing, historical EP24 deployment documented in [issue #258](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/issues/258). This page is **not** an instruction to develop new EP24 features in this AI26-focused repository, redeploy a service, change network access, or publish operational details.
>
> **Evidence status:** the host observations recorded in issue #258 are a snapshot from **2026-11-16**. They are not a continuous health check or an assertion about the host's present state. Re-verify them before any operation.

## 1. Find the authoritative runtime state first

This repository's example service file, prior Laskin-oriented instructions, and the service observed in issue #258 **are not the same deployment configuration**. Do not infer the current live unit from a checked-in example.

On the **authorized** dashboard host, an operator may inspect:

```bash
systemctl --user status ep24-dashboard-pouta.service
systemctl --user cat ep24-dashboard-pouta.service
systemctl --user show ep24-dashboard-pouta.service --property=FragmentPath,DropInPaths,ExecStart,EnvironmentFiles
git -C "$DASHBOARD_CHECKOUT" status --short --branch
git -C "$DASHBOARD_CHECKOUT" rev-parse HEAD
git -C "$DASHBOARD_CHECKOUT" rev-parse origin/main
```

Here `DASHBOARD_CHECKOUT` is the **verified** live checkout path, supplied by the operator, not a value to guess. Avoid pasting environment values, passwords, sensitive paths, or full unit output into public tickets or logs. A service called `ep24-dashboard-pouta.service` is a **user** unit: do not substitute `sudo systemctl`.

Record: unit name; current checkout SHA; remote SHA; chosen data snapshot identifier and manifest identity; whether the service is running; and the validation outcome. Keep sensitive host details in an authorized private location.

## 2. Code changes are reviewed, deployments are separate

The production checkout is not the editing workspace. For an explicitly authorized compatibility fix:

1. Create a short-lived branch from current `main` in a development checkout. Make a small PR and use synthetic tests and `python scripts/check_public_tree.py`. Follow `AGENTS.md`, including its prohibition on new EP24 development by default.
2. Verify `ruff check .` and `pytest` (or record which checks cannot be executed and why). Review the change before merging.
3. **Only with explicit deployment authorization**, record the previous served SHA, confirm the live checkout is clean, fast-forward from the reviewed branch via `main`, then restart only the existing **user** service.
4. Check user-service status, localhost Streamlit health, application logs and **a rendered real-data panel**. HTTP 200 alone is not acceptance.
5. Log the served SHA, snapshot identifier, manifest/hash verification, and observed app behavior. For rollback, restore the **recorded** previously working revision and snapshot selection, then revalidate.

Do not edit tracked application files in the live checkout, manually alter packages in its venv, run another Streamlit instance on the live port, or assume `git pull` itself proves the deployment works.

The issue reports historical commit drift. **Do not automatically fix it while reading this document.** A live code update is a deployment decision.

## 3. Treat exports as immutable snapshots

The existing dashboard consumes an export snapshot read-only. **Changing code does not imply refreshing data**, and refreshing data does not imply editing code.

For an explicitly approved refresh, the authorized producer creates a new named snapshot and its provenance artifacts. Validate its `manifest.json`, `dictionary.json`, relevant CSV hashes, cohort identity and per-country counts **using the manifest's record-unit/identity definitions**, not an assumed row count. Compare the old and new snapshots. Only after validation, sync to a distinct directory; switch the configured snapshot reference; restart and verify rendered panels. Retain the prior snapshot until rollback is no longer required.

Never overwrite or delete the live snapshot in place, nor silently regenerate research annotations during a dashboard deployment. Some older refresh procedures use different manifest naming or record-unit conventions; inspect the actual exporter version and artifacts before applying their commands.

See [the historical refresh guide](EP24_DASHBOARD_REFRESH.md) and [the issue #242 acceptance record](EP24_242_ACCEPTANCE.md), but treat neither as proof of current host state.

## 4. Private data and credentials

This **public** repository must never contain private EP24 rows, author usernames, video IDs, transcripts, OCR, exported CSV/JSONL bundles, unpublished codebooks, researcher notes, source media, tokens, secrets, or machine-specific host configuration.

Authorized private export material belongs in the private study workspace (and, where approved by its rules, in `TomiToivio/LaclauGPT-Private` under `analysis/ep24/`), with run provenance, manifest and checksums. **Before writing to the private repository, read its current `AGENTS.md`, `.gitattributes` and relevant branch policy.** Do not apply a historical phase-branch instruction from issue #258 over newer repository rules without checking. Respect Git LFS where configured, and verify that a retrieved CSV is actual content rather than an LFS pointer.

Raw source media should remain in the approved protected media store, not in Git. A private repository is not automatically an authorized storage destination for all restricted research materials. Dashboard passwords belong in protected host-local configuration, not Git or public issue comments.

The dashboard's environment variable `LACLAUGPT_VIS_ANALYSIS_DATA_DIR` selects the snapshot; it is not permission to mutate that directory.

## 5. Owner decisions, not default agent actions

Issue #258 identifies a possible difference between the observed live access configuration and the protective example deployment configuration. **No agent should change binding address, firewall, authentication, password gate, proxy, TLS or VPN settings without an explicit owner decision**. Because these exports contain sensitive research material, treat the absence of an access gate as a security concern to escalate promptly, not as proof public exposure was approved.

Likewise, the observed live-versus-`main` revision difference must not be silently resolved. Ask for explicit deployment authorization before updating the served revision.

## 6. Completion checklist

- [ ] The owner-authorized host, user unit, served SHA and deployed data snapshot were verified **at the time of work**.
- [ ] The change was reviewed in a branch/PR and public-tree, lint and test checks were executed or their absence documented.
- [ ] No private row-level data, credentials or host configuration entered public Git, issue comments or logs.
- [ ] An export refresh, if requested, used a new immutable snapshot with manifest/identity/hash checks and rollback retention.
- [ ] Any approved deployment recorded previous SHA, clean checkout, the deployed SHA, localhost health, log review and rendered-panel verification.
- [ ] No network access or authentication policy changed without explicit owner approval.
- [ ] Unknowns and blockers are reported; a successful restart, green CI and a past issue observation are **not** evidence of current operational correctness.

**Related:** [issue #258](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/issues/258) is the host-observation record; [`AGENTS.md`](../AGENTS.md) remains authoritative for current repository development and privacy rules.
