# AI26 dashboard on Laskin

This is the public, secret-free deployment runbook for the AI26 visualization service on Laskin. The deployment uses the unified Visualization application and the canonical Collection → Analysis → Visualization contract. It does not fork analysis logic or embed private AI26 settings in this repository.

## Development branch

- `main` is the canonical active development branch. Create short-lived branches from `main` and merge validated changes back.
- Research phases belong to the papers (Paper 1–4) and do not determine branch selection.
- Historical `phase-N` branches are inert snapshots and must not receive new work.
- Select AI26 explicitly with `LACLAUGPT_VIS_PROJECT_ID=ai26`.
- The current AI26 default browser/data contract is `canonical`; select it with `LACLAUGPT_VIS_BROWSER_DATA_CONTRACT=canonical`. Use `phase0` only as an explicit historical compatibility override.
- The dashboard is a human-in-the-loop research interface. It presents upstream evidence and analysis for review; it does not perform discourse inference.
- Descriptive prominence is not theoretical proof. Frequency is not hegemony, graph centrality is not nodal status, proximity is not equivalence, and a conflict edge or two-cluster layout is not by itself antagonism or polarisation.
- Private codebooks, credentials, hostnames, researcher notes, row-level research data and machine-specific paths stay outside the public repository.

## Runtime layout

No Laskin path is hard-coded in the repository. Choose the deployment paths locally and expose them through the service template or environment:

```bash
export LACLAUGPT_VIS_REPO_ROOT=/path/to/LaclauGPT-Data-Visualization
export LACLAUGPT_VIS_ENV_FILE=/path/to/private/ai26-visualization.env
export LACLAUGPT_VIS_VENV="$LACLAUGPT_VIS_REPO_ROOT/.venv"   # optional override
```

The private environment file should point runtime writes at a private data root and may configure optional remote adapters. A sanitized tracked template is maintained at `TomiToivio/LaclauGPT-Private/visualization/ai26/laskin.env.example`; copy it to the protected runtime location and replace placeholders there. The systemd example also pins the canonical browser contract explicitly so `ExecStartPre` and `ExecStart` cannot disagree. A production-style AI26 profile is:

```dotenv
LACLAUGPT_VIS_PROFILE=server
LACLAUGPT_VIS_MACHINE=linux-server
LACLAUGPT_VIS_EXECUTION=web-service
LACLAUGPT_VIS_PROJECT_ID=ai26
LACLAUGPT_VIS_BROWSER_DATA_CONTRACT=canonical

# Query/runtime policy. Keep secrets in the private environment only.
LACLAUGPT_VIS_STORAGE_BACKEND=mongodb
LACLAUGPT_VIS_DATA_BACKEND=mongodb
LACLAUGPT_VIS_CACHE_BACKEND=redis
LACLAUGPT_VIS_MESSAGING_BACKEND=redis
LACLAUGPT_VIS_OBJECT_BACKEND=local

LACLAUGPT_VIS_RELEASE_SHA=<reviewed-full-git-commit>
LACLAUGPT_VIS_SERVER_HOST=<Laskin-tailnet-IPv4>
LACLAUGPT_VIS_SERVER_PORT=8504
LACLAUGPT_VIS_DATA_DIR=/private/runtime/ai26/visualization
LACLAUGPT_VIS_OUTPUT_DIR=/private/runtime/ai26/visualization/exports
```

MongoDB, Redis and S3-compatible/Allas settings are optional application capabilities and must be supplied only when the corresponding backend is selected. CI and public tests use synthetic/local data and do not require any remote service.

The supported storage hierarchy is:

1. canonical local/runtime files as fallback,
2. MongoDB for canonical records/analysis when configured,
3. Redis for optional cache, pub-sub and operational state,
4. S3-compatible/Allas references for artifacts when configured.

AI26 and other studies remain isolated through the explicit `project_id` namespace.

## Install

```bash
cd "$LACLAUGPT_VIS_REPO_ROOT"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[remote]'
```

For development validation:

```bash
.venv/bin/pip install -e '.[remote,dev]'
python scripts/check_public_tree.py
.venv/bin/ruff check .
.venv/bin/pytest
npm run test:legacy
```

## Preflight and health

The preflight derives the repository root from its own location unless `LACLAUGPT_VIS_REPO_ROOT` is provided. The private env path must be explicit:

```bash
export LACLAUGPT_VIS_ENV_FILE=/path/to/private/ai26-visualization.env
bash deploy/preflight-laskin-ai26.sh
```

It verifies AI26 selection, the active `main` branch contract, the canonical browser contract, Linux web-service execution, safe binding, retirement of obsolete legacy services, and then runs the sanitized application commands:

```bash
.venv/bin/laclaugpt-visualize profile
.venv/bin/laclaugpt-visualize health
```

`profile` and `health` both expose the effective non-secret `browser_data_contract`, so an operator can verify that the running service selected `canonical` without printing credentials. Optional capability failures must be shown as unavailable/degraded rather than causing unrelated views to crash.

### Deployment drift and dependency guard (#234)

The same drift was shipped three times: #176 (58 commits behind), #185, and #234 (13 commits behind on a feature branch, serving 200 the whole time). The preflight therefore asserts, before anything is restarted:

* the serving checkout is on `main` **and** equal to `origin/main` (it fetches first, and falls back to the local `origin/main` ref with a warning if the fetch fails);
* every requirement in `[project].dependencies` is installed in the venv that will serve the unit, at a satisfying version. It reads `pyproject.toml`, not the installed distribution metadata, because the stale editable-install metadata was what hid the missing `networkx` in #234.

Both assertions fail closed with an `ERROR:` line naming the served SHA versus `origin/main` or the missing distribution. Two explicit overrides exist:

```bash
LACLAUGPT_VIS_ALLOW_GIT_DRIFT=1 bash deploy/preflight-laskin-ai26.sh   # deploy a branch on purpose
LACLAUGPT_VIS_GIT_FETCH=0 bash deploy/preflight-laskin-ai26.sh         # no network; compare local ref
```

The guard lives in `deploy/preflight-checkout-ai26.py` and can be run alone:

```bash
.venv/bin/python deploy/preflight-checkout-ai26.py --repo-root .
```

## systemd

Use `deploy/laclaugpt-visualization-laskin-ai26.service.example` as a template. Replace these placeholders locally:

- `<service-user>` and `<service-group>`
- `<visualization-root>`
- `<private-env-file>`
- `<private-runtime-root>`

The checked-in template deliberately contains no credential, private hostname or Laskin-specific filesystem path. It does contain `Environment=LACLAUGPT_VIS_BROWSER_DATA_CONTRACT=canonical`; the protected environment file should carry the same value. The preflight intentionally fails if that effective value is anything else.

## Retire the legacy split deployment

The legacy JSONL dashboard/export path from the former monolithic deployment is not part of the supported visualization service. Before enabling the unified service, confirm each unit belongs exclusively to the obsolete dashboard and has no remaining consumers. For confirmed units:

```bash
systemctl --user disable --now ai26-dashboard.service ai26-export.service ai26-export.timer 2>/dev/null || true
```

A direct-Streamlit unit is the same retired shape under a new name — on Laskin it appeared as
`laclaugpt-ai26-dashboard.service`, which is why the command above also has to name it explicitly:

```bash
systemctl --user disable --now laclaugpt-ai26-dashboard.service 2>/dev/null || true
```

Disable it rather than only stopping it: `stop` leaves it `enabled`, so the next login starts two units
for one port and the outcome depends on the race.

Do not re-enable an obsolete exporter merely to feed the dashboard. If a portable export is introduced later, write it through a temporary file plus atomic rename rather than truncating a live file before replacement.

## Researcher-facing verification

After start, verify that:

1. the active project is `ai26` and the browser contract is `canonical`;
2. Monitor shows corpus size, analyzed versus awaiting-analysis state, source/platform activity and descriptive formation/signifier/actor summaries;
3. Researcher Review preserves stable `source_url`, evidence, summary, structured analysis, provenance, uncertainty/abstention and human review state;
4. Explore renders timeline and available formation/topic/entity/signifier distributions;
5. graph/SNA views appear only when an explicit upstream network product exists;
6. newly written Collection → Analysis outputs become visible through the configured runtime backend without code changes;
7. records awaiting analysis, malformed/rejected records, stale data, empty filters and unavailable optional services produce useful states instead of crashes;
8. AI26 data does not mix with Brazil26 or any other project namespace;
9. no visualization-side discourse inference is performed.

## Single-service cutover and rollback (#330)

Use the Laskin system service `laclaugpt-visualization-ai26.service`. The external EP24 hosts are outside this migration. Operate locally on Laskin. Keep private inventories, unit backups, prior release SHA, dependency versions and data paths in the private runtime directory. Use the existing canonical AI26 data source.

1. Inventory all four ports with `sudo ss -ltnp '( sport = :8501 or sport = :8502 or sport = :8503 or sport = :8504 )'`. For each listener, inspect its PID, cgroup, working directory and parent process. Check system and relevant user `systemctl list-unit-files` and `list-timers --all`, container restart policies, Compose definitions, cron and login/startup jobs. Check disabled/inactive units too. Match names to executable, project and paths. Record dependencies and any unrelated consumers before changing an owner.
2. Inspect `git worktree list --porcelain`. Preserve all worktrees and data. If a retired checkout holds main, coordinate with its owner before releasing the branch. Choose a clean canonical checkout at the reviewed main commit. Set its full SHA in the private environment. Retain a private dependency snapshot (`python -m pip freeze --exclude-editable`) from the tested release venv for replay on the same Python/platform. Restore it with `pip install -r` before installing the release with `pip install --no-deps -e .`.
3. Confirm actual tailnet policy grants the researchers access and denies unauthorized peers, including forwarded/proxied access. Review Tailscale Serve/Funnel and reverse proxies. Remove obsolete application gate variables from this service's private environment. Set the literal authorized IPv4 returned by `tailscale ip -4` and port 8504. The startup check verifies the local bind. ACLs and upstream exposure require the independent host/network checks.
4. Stop the old service on every dashboard port, including the previous 8504 owner. For each identified obsolete system or user unit, use `systemctl disable --now UNIT` in its owning manager (system units require sudo). Disable matching timers/sockets before services. For container-managed services, first remove the dashboard-specific restart/autostart policy and stop the verified dashboard container. Preserve volumes. Back up and retire only the confirmed obsolete dashboard configuration after checking reverse dependencies. Preserve unrelated exporters, units, source and research material. Reload the changed managers and recheck inactive/disabled state.
5. Install the customized system service. Load its protected environment in the operator shell, run the preflight, and then start the single service.

```bash
set -a
. "$LACLAUGPT_VIS_ENV_FILE"
set +a
bash deploy/preflight-laskin-ai26.sh
sudo systemctl daemon-reload
sudo systemctl enable --now laclaugpt-visualization-ai26.service
bash deploy/check-laskin-listeners.sh serving
curl --fail --noproxy '*' "http://$LACLAUGPT_VIS_SERVER_HOST:8504/_stcore/health"
export LACLAUGPT_VIS_DEPLOYMENTS="ai26=8504:$LACLAUGPT_VIS_REPO_ROOT#laclaugpt-visualization-ai26.service"
sudo --preserve-env=LACLAUGPT_VIS_DEPLOYMENTS .venv/bin/python deploy/served-drift-report.py
```

6. From an authorized researcher browser, open the private endpoint on 8504. Verify there is no login prompt, real AI26 coverage and analysis freshness agree with the source, filters update charts and evidence, and all available network layers render. Verify rejected access from an unauthorized vantage point. Confirm the service working directory and release SHA against the reviewed revision. Repeat the listener and browser checks after a service-manager reload and again after the next authorized host reboot. Record the endpoint, commit, sanitized checks and outstanding checks in #330. Keep the issue open until live acceptance.
7. For rollback, stop the unit, restore the previously verified single-service checkout, matching virtualenv and pinned SHA. A rollback to an older reviewed commit requires the documented intentional git-drift override. Keep the private address, port 8504, and network restriction. Rerun preflight and the listener/health/browser tests. If there is no previously verified consolidated release, keep the service stopped and record the failed cutover.
