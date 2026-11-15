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

LACLAUGPT_VIS_SERVER_HOST=127.0.0.1
LACLAUGPT_VIS_SERVER_PORT=8501
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

After installing the customized unit:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now laclaugpt-visualization-ai26.service
sudo systemctl status laclaugpt-visualization-ai26.service
sudo systemctl restart laclaugpt-visualization-ai26.service
journalctl -u laclaugpt-visualization-ai26.service -n 200 --no-pager
```

A user-service installation is also valid. Remove `User=` and `Group=`, install under `~/.config/systemd/user/`, use `WantedBy=default.target`, and run the equivalent `systemctl --user` commands.

## Retire the legacy split deployment

The legacy JSONL dashboard/export path from the former monolithic deployment is not part of the supported visualization service. Before enabling the unified service, retire those units if present:

```bash
systemctl --user disable --now ai26-dashboard.service ai26-export.service ai26-export.timer 2>/dev/null || true
```

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

### Distinct worktree ownership for :8501 and :8503 (#236)

The canonical AI26 dashboard on :8501 owns branch `main`. A second
worktree for a separate :8503 live-steps instance **must not claim `main`**:
Git forbids checking the same branch out in two normal worktrees, which
previously left the :8501 refresh on a maintenance branch. The #234 preflight
now also fails if `git worktree list --porcelain` shows another worktree
claiming `main`. This is a read-only assertion and will not modify either
deployment.

To inspect the host before any change:

```bash
git -C "$LACLAUGPT_VIS_REPO_ROOT" worktree list
git -C "$LACLAUGPT_VIS_REPO_ROOT" status --short
# Check the :8503 worktree separately (substitute its configured path):
git -C "$LIVE_STEPS_WORKTREE" status --short
git -C "$LIVE_STEPS_WORKTREE" branch --show-current
```

**Do not run `git worktree remove`, `git reset --hard`, `git stash`,
`git clean` or `git switch --discard-changes` against the :8503 checkout.**
The #236 incident documented staged edits and deletion belonging to another
session. Preserve them exactly as found.

For an **already clean** :8503 worktree, switch to a deployment-specific branch:

```bash
# Only after verifying the :8503 checkout is CLEAN, and main is at
# the intended tested commit:
git -C "$LIVE_STEPS_WORKTREE" switch -c deploy/live-steps
# If that branch already exists, use "switch deploy/live-steps" instead.
git -C "$LACLAUGPT_VIS_REPO_ROOT" switch main
git -C "$LACLAUGPT_VIS_REPO_ROOT" pull --ff-only origin main
```

Alternatively a clean :8503 worktree may be detached at a reviewed SHA using
`git switch --detach <reviewed-sha>`. Never detach or switch while it contains
someone else's uncommitted work. If :8503 is dirty, **stop and coordinate with
the owner of that work**; do not force the :8501 checkout onto main with
`--ignore-other-worktrees`. Once :8503 no longer claims main, refresh :8501
using the documented main-branch commands and run the preflight before
restarting. Do not start or deploy :8503 merely to fix branch ownership.

## Update and restart

One clone may serve more than one dashboard. A git branch can be checked out in only one worktree,
so the AI26 checkout on `:8501` owns `main`; any additional deployment must be a **detached**
worktree so it never claims the branch (#236).

```bash
cd "$LACLAUGPT_VIS_REPO_ROOT"
git status --short
git switch main                 # stop if another worktree owns main
git pull --ff-only origin main
.venv/bin/pip install -e '.[remote]'
bash deploy/preflight-laskin-ai26.sh
sudo systemctl restart laclaugpt-visualization-ai26.service
sudo systemctl status laclaugpt-visualization-ai26.service
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
:8501 to `main`. The preflight refuses conflicting branch ownership rather
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
must be the configured path, the branch must be `main`, and HEAD must equal `origin/main`. It also
reports a branch claimed by **two deployments**, the #236 layout defect that makes the documented
refresh impossible to run non-interactively. A duplicate claim held only by a transient scratch
worktree is reported as a note, not a failure.

The deployments are the documented two on Laskin and can be overridden:

```bash
# The deployment paths are host state, not repository content: name them here or in
# LACLAUGPT_VIS_DEPLOYMENTS (comma separated, NAME=PORT:PATH).
.venv/bin/python deploy/served-drift-report.py \
  --deployment "ai26-dashboard=8501:$LACLAUGPT_VIS_REPO_ROOT" \
  --deployment "live-steps=8503:$LIVE_STEPS_WORKTREE@detached"
```

`@detached` marks a secondary deployment: per the convention above it must serve a commit, not a
branch, so a detached HEAD there is correct. The same rule inverted applies — a *secondary*
deployment found on `main` is reported as the #236 layout defect.

### Install the hourly report

`deploy/laskin-served-drift.service.example` and `.timer.example` run it hourly and append to
`<private-runtime-root>/logs/served-drift.log`; both a drift and a healthy run are recorded, and the
exit status is preserved for a watcher. Fill in the two paths, install into
`~/.config/systemd/user/`, then `systemctl --user enable --now laskin-served-drift.timer` — and
`loginctl enable-linger "$USER"`, otherwise the timer dies with the login session.

## Logs and privacy

Use the service manager journal for process logs. Do not paste logs into public issues without checking for research content, private endpoints, credentials or private provenance paths. Runtime data and researcher notes must remain under the configured private runtime root, never inside the public Git checkout.
