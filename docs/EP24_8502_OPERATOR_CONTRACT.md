# EP24 :8502 researcher dashboard: agent operating contract

> Legacy EP24 operational exception. Issue [#258](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/issues/258) records a **2026-11-16 host observation**, not a continuously verified deployment status. Follow the active AI26 defaults in [AGENTS.md](../AGENTS.md) for all other work. Do not extend the dormant EP24 implementation beyond explicitly requested maintenance.

## Before changing anything

1. Verify the actual service, deployed commit, data directory and network exposure on the host with authorized access. Never assume an example unit matches the installed user unit.
2. Check whether another agent already has an open PR or deployment in progress.
3. Separate **code deployment** from **data refresh**. The dashboard reads a read-only export snapshot; restarting Streamlit does not refresh data.
4. Treat any externally accessible researcher dashboard as potentially sensitive. An HTTP 200 health check does not establish authorization or safe exposure.

The issue records a user-level systemd unit called `ep24-dashboard-pouta.service`, the Streamlit entry point `src/laclaugpt_visualization/ep24_reprocessed_app.py`, and environment variable `LACLAUGPT_VIS_ANALYSIS_DATA_DIR`. These details must be rechecked rather than taken as permanent.

## Code change, deployment, verification

Make changes in a short-lived branch from current `main`, run the public-tree, lint and test checks, and open a PR. **Never edit tracked code in the served checkout.** After review and merge, an authorized operator on the deployment host can:

```bash
cd /path/to/served/LaclauGPT-Data-Visualization
git status -sb
git rev-parse HEAD                    # record rollback SHA
git fetch origin
git pull --ff-only origin main       # only if checkout is clean
systemctl --user restart ep24-dashboard-pouta.service
systemctl --user is-active ep24-dashboard-pouta.service
curl -fsS http://127.0.0.1:8502/_stcore/health
git rev-parse HEAD                    # record served SHA
```

Inspect logs and load a real dashboard panel in a browser; an active service and healthy endpoint do not prove that data, filters or charts render correctly. If rollback is needed, restore the recorded deployment SHA through an authorized controlled procedure and restart. Do not blindly use `git reset --hard` on a dirty checkout.

Never install dependencies ad hoc into the live virtual environment, delete or modify live export files, or start another Streamlit instance on the occupied port. If the deployment host is inaccessible, record this as **unverified**, not successful.

## Data snapshot change (independent of code deployment)

- Produce exports using the canonical exporter on an authorized producer machine. Consult [EP24 dashboard refresh](EP24_DASHBOARD_REFRESH.md) and [acceptance checks](EP24_242_ACCEPTANCE.md). Existing instructions for other historical units/hosts are not automatic deployment commands for this `:8502` service.
- Stage a **new sibling snapshot directory** rather than overwriting the served directory. Keep the old snapshot intact until post-switch verification.
- Require `manifest.json`, `dictionary.json`, the relevant CSVs and all required child tables. Verify per-country record identity and counts against the manifest, and verify CSV SHA-256 checksums when supplied. Different video/ingest identity rules can yield different legitimate totals.
- Switch `LACLAUGPT_VIS_ANALYSIS_DATA_DIR` in the host-local systemd configuration only after validation. Restart the service, verify rendered panels and record the deployed SHA, snapshot identity, record-unit/identity rule and checksums.
- Never infer freshness from counts alone: analysis steps can advance without adding rows. Missing or incomparable provenance is a reason to stop and investigate, not a reason to force a swap.

## Private data and secrets

This is a **public code repository**. Never commit real export snapshots, source identifiers, author names, transcripts, review notes, private codebooks, host credentials, secret values or sensitive configuration here.

The Git-backed home for authorized private research artifacts is `TomiToivio/LaclauGPT-Private`, under `analysis/<study>/`. **Read that repository's current `AGENTS.md` and branch policy first**; its rules are independent of this repository's continuous-`main` policy. Its large CSV/JSON/database files may be Git LFS pointers: verify `git lfs pull` completed and confirm actual bytes and content hashes in a fresh checkout. Preserve producer/run provenance and manifests. Source video/images belong in approved object storage, not automatically in private Git.

Keep dashboard passwords in a host-local, mode-`0600` environment file, never in repository files, comments or logs. An unset password may mean open access: do not silently interpret this as safe.

## Owner decisions and release hold

Issue #258 reported (on 2026-11-16) that the live service was listening on all network interfaces **without a configured password**, and the checkout was behind `main`. These are historical observations until reverified.

1. **Access policy requires owner approval:** restrict to private network and authenticated access, or explicitly authorize the currently open access. Do not change audience/reachability silently.
2. **Deploying updated `main` requires an authorized deployment and post-deploy verification**. A documentation-only PR does not itself deploy code or solve drift.

Record: approver, deployment UTC time, old/new served SHA, old/new snapshot, manifest hash, access-policy decision, user-unit status, health response, and browser-rendered panel outcome. Do not mark the issue fully implemented on the strength of documentation or a health endpoint alone.
