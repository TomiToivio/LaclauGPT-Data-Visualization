# AI26 dashboard on NooPunk

This is the public, secret-free runbook for the **on-demand** AI26 visualization
service on **NooPunk**. It is the counterpart to
[`AI26_LASKIN_DASHBOARD.md`](AI26_LASKIN_DASHBOARD.md): same application, same
canonical AI26 contract, different runtime policy.

NooPunk is the **always-on browser collection node** and the **on-demand test
workstation**. Visualization here is for local user testing — it runs when the user
starts it and stops when they stop it. **Laskin remains the always-on
analysis/visualization node.** See
[`AI26_EXECUTION_ARCHITECTURE.md` in the main repository](https://github.com/TomiToivio/LaclauGPT/blob/main/docs/AI26_EXECUTION_ARCHITECTURE.md)
for the two-machine roles and `LaclauGPT#71` for the task.

The dashboard is a human-in-the-loop research interface. It presents upstream evidence
and analysis for review; it **does not perform discourse inference**, and **it must not
trigger analysis merely because the UI started** (see "Starting the dashboard must not
start analysis" below).

## Active branch contract

- `main` is the canonical active/stable Phase 2 development branch.
- Select AI26 explicitly with `LACLAUGPT_VIS_PROJECT_ID=ai26`.
- Select the canonical browser contract with `LACLAUGPT_VIS_BROWSER_DATA_CONTRACT=canonical`.
- Private codebooks, credentials, hostnames, researcher notes, row-level research data
  and machine-specific paths stay outside the public repository. NooPunk's real values
  live in `TomiToivio/LaclauGPT-Private` under the NooPunk layout, not here.

## What NooPunk reads: the same store as Laskin

NooPunk must not fork the corpus. It reads the **same** AI26 MongoDB, the same Redis
plane when configured, and the same CSC Allas / S3 object layout as Laskin, under one
`ai26` namespace. The only thing that differs is *which node is running the process*.

```dotenv
LACLAUGPT_VIS_PROFILE=local
LACLAUGPT_VIS_MACHINE=laptop
LACLAUGPT_VIS_EXECUTION=web-service
LACLAUGPT_VIS_PROJECT_ID=ai26
LACLAUGPT_VIS_BROWSER_DATA_CONTRACT=canonical

# The same adapters Laskin uses. NooPunk is not a degraded read-only mirror; it
# selects the same backends so the test workstation exercises what Laskin runs.
LACLAUGPT_VIS_STORAGE_BACKEND=mongodb
LACLAUGPT_VIS_DATA_BACKEND=mongodb
LACLAUGPT_VIS_CACHE_BACKEND=redis
LACLAUGPT_VIS_MESSAGING_BACKEND=redis
LACLAUGPT_VIS_OBJECT_BACKEND=s3
```

`LACLAUGPT_VIS_MACHINE=laptop` records the machine **class** — NooPunk is an
interactive workstation, where Laskin is `linux-server`. The field is not a hostname:
it accepts only `laptop|linux-server|custom`, and the distributed-run schema's
`machine_role` likewise uses classes (`laptop|roihu|linux-server`). Host identity is
**execution** provenance recorded separately, never study identity. A machine never
creates its own database, bucket, project ID, run ID or codebook — that rule is what
keeps the two nodes one system. Do not "fix" a connection problem locally by pointing
NooPunk at a local database instead of the shared one.

### Local ports

| Service | Default | Notes |
| --- | --- | --- |
| AI26 dashboard | `127.0.0.1:8501` | bound to localhost by default; do not expose publicly |
| Local Ollama (analysis) | `127.0.0.1:11434` | consumed by the Analysis runbook, not by the dashboard |

If a port is already in use, change `LACLAUGPT_VIS_SERVER_PORT` rather than binding a
wider address: NooPunk is an interactive workstation and the dashboard is a test
surface, not a public service.

### Dependencies

- A checkout of `LaclauGPT-Data-Visualization` and a local virtualenv.
- Network reachability to the shared AI26 MongoDB / Redis / Allas endpoints. If those
  are unreachable the service must report **degraded/unavailable**, not silently fall
  back to a local corpus.
- No GPU requirement: the dashboard is a read and presentation surface.

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
.venv/bin/ruff check . && .venv/bin/pytest
```

## Preflight and health

```bash
export LACLAUGPT_VIS_REPO_ROOT=/path/to/LaclauGPT-Data-Visualization
export LACLAUGPT_VIS_ENV_FILE=/path/to/private/noopunk-ai26-visualization.env
bash deploy/preflight-noopunk-ai26.sh
```

The preflight checks AI26 selection, the canonical browser contract, the
NooPunk execution profile, localhost-safe binding, and then runs the sanitized
application commands:

```bash
.venv/bin/laclaugpt-visualize profile
.venv/bin/laclaugpt-visualize health
```

Both expose the effective non-secret `browser_data_contract`, so the running service's
contract can be confirmed without printing credentials.

## Start and stop

The user experience for NooPunk is deliberately three commands per surface. The
wrapper is `scripts/ai26-noopunk.sh`:

```bash
scripts/ai26-noopunk.sh start visualization     # start the dashboard
scripts/ai26-noopunk.sh stop  visualization     # stop it
scripts/ai26-noopunk.sh status visualization    # is it running, and on what contract
```

Underlying behaviour, if you prefer to run it by hand:

```bash
set -a; . "$LACLAUGPT_VIS_ENV_FILE"; set +a
exec "$LACLAUGPT_VIS_REPO_ROOT/.venv/bin/laclaugpt-visualize" serve
```

`stop` stops only NooPunk's dashboard process. It must never stop, restart or
reconfigure anything on Laskin; the two nodes coordinate through the shared contract,
not through administrative control of each other.

## Starting the dashboard must not start analysis

This is an explicit AI26 requirement and worth stating where an operator will read it:
**bringing the UI up must not enqueue, claim or run analysis work.** The dashboard is a
read surface. If analysis starts as a side effect of opening the UI, that is a defect —
NooPunk is an interactive workstation, and a testing session that silently consumes the
shared queue would also take work away from Laskin.

Consequences to preserve:

- records awaiting analysis remain visible and must not break the dashboard;
- no analysis job is claimed by the visualization process;
- an empty or partially-analysed corpus renders a useful state rather than an error.

## systemd (optional)

NooPunk does not need a permanent background service. If you want one, a **user**
service is the appropriate form for an interactive workstation — install under
`~/.config/systemd/user/`, use `WantedBy=default.target`, and run `systemctl --user`
commands. A system-wide unit is also possible but is not required and not recommended
by default for a test surface the user starts deliberately.

## Researcher-facing verification

After start, verify that:

1. the active project is `ai26`, the browser contract is `canonical`, and the machine
   class reads `laptop` (NooPunk), not Laskin's `linux-server`;
2. the corpus shown is the **shared** one — a record collected or analysed on Laskin is
   visible here without any local copy;
3. Monitor, Researcher Review, Explore and graph/SNA views behave as described in the
   Laskin runbook;
4. newly written Collection → Analysis outputs become visible through the configured
   backend without code changes;
5. records awaiting analysis, malformed/rejected records, stale data, empty filters and
   unavailable optional services produce useful states instead of crashes;
6. AI26 data does not mix with any other project namespace;
7. no visualization-side discourse inference is performed;
8. **starting the UI enqueued nothing**: the shared queue depth is unchanged by the
   dashboard coming up.

## Cross-machine reconnect

NooPunk must be able to keep collecting browser data while Laskin is unavailable, and
then continue cleanly when the shared services are reachable again. For the dashboard
that means: a temporarily unreachable MongoDB/Redis/Allas is reported as degraded, the
UI stays up, and no local fallback corpus is created. Whether the *collection* buffering
behind that is sufficient is owned by the Collection runbook; the dashboard's job is to
not compound the problem by forking state.

## Update and restart

```bash
cd "$LACLAUGPT_VIS_REPO_ROOT"
git status --short
git pull --ff-only
.venv/bin/pip install -e '.[remote]'
bash deploy/preflight-noopunk-ai26.sh
scripts/ai26-noopunk.sh restart visualization
```

## Logs and privacy

Use the process journal or the wrapper's log. Do not paste logs into public issues
without checking for research content, private endpoints, credentials or private
provenance paths. Runtime data and researcher notes stay under the configured private
runtime root, never inside the public Git checkout.

## What this runbook deliberately does not contain

No hostname, port, URI, bucket name, account, credential or private filesystem path for
NooPunk or Laskin. Those live in `LaclauGPT-Private`. This file is the public procedure;
the private repository is the deployment.

## Related

- [`AI26_LASKIN_DASHBOARD.md`](AI26_LASKIN_DASHBOARD.md) — the always-on node
- [`AI26_CONFIGURATION.md`](AI26_CONFIGURATION.md) — configuration surface
- [`AI26_DASHBOARD.md`](AI26_DASHBOARD.md) — the dashboard surface generally
- `TomiToivio/LaclauGPT` → `docs/AI26_EXECUTION_ARCHITECTURE.md` — the two-machine contract
- `TomiToivio/LaclauGPT` → `skills/hermes-ai26-operations/SKILL.md` — bounded verification
