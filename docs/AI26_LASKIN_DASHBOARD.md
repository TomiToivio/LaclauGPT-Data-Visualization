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
LACLAUGPT_VIS_OBJECT_BACKEND=s3

LACLAUGPT_VIS_SERVER_HOST=<verified-private-interface-IPv4>
LACLAUGPT_VIS_SERVER_PORT=8504
LACLAUGPT_VIS_NETWORK_ACCESS_VERIFIED=1
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

## Start manually

```bash
set -a
. "$LACLAUGPT_VIS_ENV_FILE"
set +a
exec "$LACLAUGPT_VIS_REPO_ROOT/.venv/bin/laclaugpt-visualize" serve
```

With `project_id=ai26`, `serve` selects the packaged AI26 research workbench. The application exposes Monitor, Explore, Networks when an explicit upstream network product exists, Records/Researcher Review, Reports and diagnostics. Records awaiting analysis remain visible and must not break the dashboard.

## systemd

Use `deploy/laclaugpt-visualization-laskin-ai26.service.example` as a template. Replace these placeholders locally:

- `<service-user>` and `<service-group>`
- `<visualization-root>`
- `<private-env-file>`
- `<private-runtime-root>`

The checked-in template deliberately contains no credential, private hostname or Laskin-specific filesystem path. It does contain `Environment=LACLAUGPT_VIS_BROWSER_DATA_CONTRACT=canonical`; the protected environment file should carry the same value. The preflight intentionally fails if that effective value is anything else.

Install the customized template under the canonical filename `ai26-dashboard.service` (not the historical template basename). Prefer the existing user-manager installation on Laskin. After installing a system-manager variant, if that is the approved host configuration:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ai26-dashboard.service
sudo systemctl status ai26-dashboard.service
sudo systemctl restart ai26-dashboard.service
journalctl -u ai26-dashboard.service -n 200 --no-pager
```

The reported #337 migration uses a user-service installation; retain that manager rather than enabling a second system unit. Remove `User=` and `Group=`, install under `~/.config/systemd/user/`, use `WantedBy=default.target`, and run the equivalent `systemctl --user` commands.

### One unit owns :8504 (#293)

`laclaugpt-visualize serve` launches `ai26_dashboard.py` through Streamlit — the same page a hand-written
`streamlit run src/laclaugpt_visualization/ai26_dashboard.py` unit would serve. The difference is what the
packaged entry point adds around it: the readiness check in `ExecStartPre`, the effective browser-data
contract, and the settings the CLI validates. The #337 migration used a direct Streamlit invocation; update the existing canonical unit in place to use the packaged entry point and preflight, rather than creating another unit.

Two units that both name `--server.port 8501` can both be `enabled`: the one that starts first wins the
port and the other dies, so a reboot can silently change which service answers. A healthy port proves
only that *something* serves it.

After install, or whenever the endpoint looks wrong, check all three facts — port, checkout, unit:

```bash
ss -ltnp | grep ':8504'                         # which pid owns the port
readlink /proc/<pid>/cwd                        # which checkout it runs from
grep -o '[^/]*\.service' /proc/<pid>/cgroup     # which unit owns it
systemctl --user is-enabled ai26-dashboard.service
```

Exactly one enabled unit may name `:8504`, and it must be the one above. `deploy/served-drift-report.py`
reports a listener owned by any other unit as drift when the deployment spec names the expected one
(`--deployment 'ai26=8504:/path#ai26-dashboard.service'`), and it also reports a listener
that no unit owns.

## Consolidate Laskin deployments (#330)

The single AI26 dashboard is the only dashboard to serve on Laskin. The private interface and URL are supplied by the operator outside Git. No Streamlit password gate is required: authorization is enforced by the private network. Do not expose a wildcard listener or public interface. Confirm the private interface ownership and network ACLs before setting the verification flag in the protected environment file. The flag records operator verification; it is not itself a network security mechanism.

Before migration, inventory listeners and both user/system services:

```bash
ss -ltnp | grep -E ':(8501|8502|8503|8504)([^0-9]|$)'
systemctl --user list-units --all
systemctl --user list-unit-files
systemctl --user list-timers --all
systemctl list-units --all
systemctl list-unit-files
systemctl list-timers --all
git worktree list
```

Check containers and other supervisor/autostart mechanisms if present. Record each listener's PID, unit, working directory, restart policy and dependencies in private deployment notes. Back up only the relevant service definitions and environment configuration securely; keep all research data and worktrees intact.

The legacy JSONL dashboard path remains retired. The host-capable agent reported the new canonical service name as `ai26-dashboard.service` in #337; do not disable the replacement unit. After confirming these exact units belong to retired deployments, known user-unit cleanup commands are:

```bash
systemctl --user disable --now laclaugpt-visualization-ai26.service laclaugpt-ai26-dashboard.service
systemctl --user disable --now laclaugpt-ep24-researcher.service laclaugpt-live-steps.service
```

Preserve independent export and backup jobs unless confirmed obsolete; the reported migration left the export timer in place. Never revive a retired exporter solely to feed the new service. Future portable exports should use a temporary file followed by atomic rename.

Stop and disable the identified old dashboard units (including the old port 8504 instance) using the appropriate manager; do not blindly kill unrelated processes or disable upstream Collection/Analysis. Remove obsolete dashboard-only autostart definitions after dependency review. Confirm all four dashboard listeners are stopped before starting the new service. Replace the canonical service configuration, set the private bind address and explicit port 8504, and run preflight. Do not restart obsolete EP24 or live-steps dashboards. Keep external EP24 reference deployments unchanged.

After starting the canonical unit, verify the private endpoint in a browser without a Streamlit login, the health endpoint, actual data and the served revision. Check that ports 8501–8503 have no dashboard listeners and that port 8504 has exactly one intended service. Check enabled/active units and timers and repeat the checks after the normal service-manager reload/restart. Verify network ACLs from an authorized client and confirm no public listener. For rollback, stop the new service and restore the saved canonical service configuration/release only; do not restore retired dashboard instances unless separately authorized.

Agents without host access should use synthetic fixtures and prepare reviewed PRs; a host-capable operator records sanitized results of these checks in issue #330.

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

### Worktree ownership (#236)

The sole AI26 service owns the clean main checkout. Preserve existing worktrees and uncommitted work; do not force-switch or delete them. Coordinate with their owners if a retired dashboard checkout still claims main. The preflight guards against conflicting worktree ownership.

## Update and restart

The sole AI26 dashboard checkout on port 8504 owns main. Retired worktrees must not claim main; preserve their changes and coordinate with their owners (#236).

```bash
cd "$LACLAUGPT_VIS_REPO_ROOT"
git status --short
git switch main                 # stop if another worktree owns main
git pull --ff-only origin main
.venv/bin/pip install -e '.[remote]'
bash deploy/preflight-laskin-ai26.sh
sudo systemctl restart ai26-dashboard.service
sudo systemctl status ai26-dashboard.service
```

If preflight fails, leave the known-good service in place and fix the configuration or checkout before restarting.

### When `main` is held by another worktree

```bash
git -C "$LACLAUGPT_VIS_REPO_ROOT" worktree list
# fatal: 'main' is already checked out at '<other worktree>'
```

Do not use `--ignore-other-worktrees`, even as a temporary workaround. First preserve
any uncommitted work in the other checkout through its owner. When clean, switch that
checkout to its own deployment branch or a reviewed detached commit, then switch
:8504 to `main`. The preflight refuses conflicting branch ownership rather
than concealing it.

## Continuous served-drift report (#234)

`deploy/preflight-laskin-ai26.sh` guards a *deploy*: it refuses to start a checkout that is not
`origin/main` with its declared dependencies installed (#235). It cannot see what happened **after**
a successful start — the drift that #176, #185, #234 and #236 all were, where the checkout moved
while the unit stayed `active` and the port kept answering 200.

`deploy/served-drift-report.py` is the continuous observer. It reads what is actually being served:

```bash
.venv/bin/python deploy/served-drift-report.py            # table, exit 1 on any problem
.venv/bin/python deploy/served-drift-report.py --fetch    # compare against a freshly fetched origin
.venv/bin/python deploy/served-drift-report.py --json     # machine-readable
```

For every deployment it ties the port to the checkout: the listening process's `/proc/<pid>/cwd`
must be the configured path, the branch must be `main`, and HEAD must equal `origin/main`. When the
spec names a unit, it also ties the port to **that unit** through the listener's cgroup, and reports
a listener owned by any other unit — or by no unit at all — as drift (#293: the port was healthy and
the unit was wrong). It also
reports a branch claimed by **two deployments**, the #236 layout defect that makes the documented
refresh impossible to run non-interactively. A duplicate claim held only by a transient scratch
worktree is reported as a note, not a failure.

Configure the single Laskin deployment:

```bash
# The deployment paths are host state, not repository content: name them here or in
# LACLAUGPT_VIS_DEPLOYMENTS (comma separated, NAME=PORT:PATH[#UNIT]).
.venv/bin/python deploy/served-drift-report.py \
  --deployment "ai26-dashboard=8504:$LACLAUGPT_VIS_REPO_ROOT#ai26-dashboard.service"
```

Two operational details, both learned the hard way (#293). The variable is `LACLAUGPT_VIS_DEPLOYMENTS`;
the script prints its own name in the error when it is unset, which is the only reason a wrong spelling
is diagnosable. And run the unit **once by hand** after installing it: the service is deliberately
`SuccessExitStatus=0 1 2`, because "drift" and "could not inspect" are reportable outcomes rather than
unit failures — so an unset variable looks exactly like a healthy run in `systemctl status`. The log is
the evidence, not the unit state.

### Install the hourly report

`deploy/laskin-served-drift.service.example` and `.timer.example` run it hourly and append to
`<private-runtime-root>/logs/served-drift.log`; both a drift and a healthy run are recorded, and the
exit status is preserved for a watcher. Fill in the two paths, install into
`~/.config/systemd/user/`, then `systemctl --user enable --now laskin-served-drift.timer` — and
`loginctl enable-linger "$USER"`, otherwise the timer dies with the login session.

## Logs and privacy

Use the service manager journal for process logs. Do not paste logs into public issues without checking for research content, private endpoints, credentials or private provenance paths. Runtime data and researcher notes must remain under the configured private runtime root, never inside the public Git checkout.
