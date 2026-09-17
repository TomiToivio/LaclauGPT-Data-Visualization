# AI26 dashboard on Laskin

This runbook is the public, secret-free operator guide for issue #35. The dashboard checkout is fixed at `/mnt/workspace/LaclauGPT-Data-Visualization`; authorized private AI26 configuration/state is fixed under `/mnt/workspace/LaclauGPT-Private`. Do not copy private values into this repository.

## Safety and source-of-truth rules

- `project_id=ai26`.
- MongoDB is the canonical durable source for collected/analyzed research data.
- Redis is transient config/status/messaging/control-plane infrastructure, not the scientific database.
- Allas/S3 is used only through the existing distributed contract. The dashboard must not download multimodal objects merely to render views.
- The service is private-network only. Keep the default loopback bind unless an existing protected reverse proxy/private subnet path is deliberately used. Do not expose the unauthenticated Streamlit service directly to the public Internet.
- Secrets, endpoints, private codebooks, notes, cookies, tokens and credentials belong in `LaclauGPT-Private`, never in this public repository or public issue comments.

## Required paths

```text
/mnt/workspace/LaclauGPT-Data-Visualization
/mnt/workspace/LaclauGPT-Private
/mnt/workspace/LaclauGPT-Private/config/ai26/visualization/laskin.env
```

Before any install/update, verify the checkout identity:

```bash
cd /mnt/workspace/LaclauGPT-Data-Visualization
pwd -P
git rev-parse --show-toplevel
```

Both outputs must be `/mnt/workspace/LaclauGPT-Data-Visualization`.

## Private environment contract

Create or maintain the real environment file only in the private repository at:

```text
/mnt/workspace/LaclauGPT-Private/config/ai26/visualization/laskin.env
```

Reuse the current AI26 distributed values already used by Collection and Analysis. Do not create a visualization-only MongoDB database, Redis namespace or project identifier.

The effective non-secret shape is:

```dotenv
LACLAUGPT_VIS_PROFILE=server
LACLAUGPT_VIS_MACHINE=linux-server
LACLAUGPT_VIS_EXECUTION=web-service
LACLAUGPT_VIS_STORAGE=distributed
LACLAUGPT_VIS_PROJECT_ID=ai26
LACLAUGPT_VIS_STORAGE_BACKEND=mongodb
LACLAUGPT_VIS_DATA_BACKEND=mongodb
LACLAUGPT_VIS_CACHE_BACKEND=redis
LACLAUGPT_VIS_MESSAGING_BACKEND=redis
LACLAUGPT_VIS_OBJECT_BACKEND=s3
LACLAUGPT_VIS_SERVER_HOST=127.0.0.1
LACLAUGPT_VIS_SERVER_PORT=8501
LACLAUGPT_VIS_DATA_DIR=/mnt/workspace/LaclauGPT-Private/runtime/ai26/visualization
LACLAUGPT_VIS_OUTPUT_DIR=/mnt/workspace/LaclauGPT-Private/runtime/ai26/visualization/exports
```

Add the actual shared MongoDB/Redis/Allas variables from the authorized private configuration. Keep their values out of shell history, logs and public Git output where possible.

## Install/update

From the exact public checkout:

```bash
cd /mnt/workspace/LaclauGPT-Data-Visualization
git status --short
git pull --ff-only
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[remote]'
```

For developer validation on Laskin, install the dev extras too:

```bash
.venv/bin/pip install -e '.[remote,dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

Do not resolve a dirty or divergent working tree by discarding local work automatically.

## Sanitized preflight

Run:

```bash
bash deploy/preflight-laskin-ai26.sh
```

The preflight verifies the exact checkout/private-root paths, the expected AI26 distributed profile shape, conservative bind behavior, and then calls the application's sanitized `profile` and `health` commands. It does not print secret connection strings.

Useful manual diagnostics:

```bash
set -a
. /mnt/workspace/LaclauGPT-Private/config/ai26/visualization/laskin.env
set +a
.venv/bin/laclaugpt-visualize profile
.venv/bin/laclaugpt-visualize health
```

The profile/health output should show `project_id=ai26`, server/linux-server execution, distributed storage, MongoDB data access and Redis capabilities without revealing credentials.

## Manual production-equivalent start

```bash
cd /mnt/workspace/LaclauGPT-Data-Visualization
set -a
. /mnt/workspace/LaclauGPT-Private/config/ai26/visualization/laskin.env
set +a
exec .venv/bin/laclaugpt-visualize serve
```

For an `ai26` profile `serve` launches `laclaugpt_visualization/ai26_dashboard.py` — the AI26 research workbench with the Monitor / Explore / Networks / Records / Reports / RAG / Configuration / Hermes / Diagnostics views. It is not the generic `app.py` workbench. The profile's project id selects the module, and `laclaugpt-visualize health` reports `not-ready` if that module is missing, so the deployment cannot silently serve the wrong dashboard.

This is suitable for verification only. Steady-state operation must be supervised by systemd or the existing equivalent service manager, not Hermes or an interactive shell.

## systemd service

Use `deploy/laclaugpt-visualization-laskin-ai26.service.example` as the source template. Replace only `<laskin-user>` and `<laskin-group>` with the authorized account/group. The template deliberately pins:

- `WorkingDirectory=/mnt/workspace/LaclauGPT-Data-Visualization`
- private environment file under `/mnt/workspace/LaclauGPT-Private`
- `.venv/bin/laclaugpt-visualize health` as `ExecStartPre`
- `.venv/bin/laclaugpt-visualize serve` as the long-running process
- restart on process failure
- public checkout read-only and private root as the only explicit writable project path
- restrictive umask and no-new-privileges hardening

Typical operator commands after installing the unit as `laclaugpt-visualization-ai26.service`:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now laclaugpt-visualization-ai26.service
sudo systemctl status laclaugpt-visualization-ai26.service
sudo systemctl restart laclaugpt-visualization-ai26.service
sudo systemctl stop laclaugpt-visualization-ai26.service
journalctl -u laclaugpt-visualization-ai26.service -n 200 --no-pager
```

### User-service variant (no root required)

On hosts without passwordless sudo the same unit works as a **user** service. Install the template under `~/.config/systemd/user/`, drop the `User=`/`Group=` lines and the `[Install] WantedBy=multi-user.target` target, and use `WantedBy=default.target`:

```bash
systemctl --user daemon-reload
systemctl --user enable --now laclaugpt-visualization-ai26.service
systemctl --user status laclaugpt-visualization-ai26.service
systemctl --user restart laclaugpt-visualization-ai26.service
systemctl --user stop laclaugpt-visualization-ai26.service
journalctl --user -u laclaugpt-visualization-ai26.service -n 200 --no-pager
```

A user service stops at logout unless lingering is enabled. Enable it once so steady-state operation does not depend on an interactive session:

```bash
loginctl enable-linger "$USER"
loginctl show-user "$USER" | grep Linger    # expect Linger=yes
```

### Manual health/status command

The readiness check is the supported way to inspect a deployment without seeing secrets:

```bash
set -a; . /mnt/workspace/LaclauGPT-Private/config/ai26/visualization/laskin.env; set +a
.venv/bin/laclaugpt-visualize health     # exit 0 = ready, 1 = not-ready
.venv/bin/laclaugpt-visualize profile    # non-secret effective configuration
```

`health` reports `not-ready` when a backend requirement is unmet or when the dashboard module for the configured project is missing, so a service that cannot serve its own dashboard is never reported healthy.

Do not paste journal output into public issues without checking it for research content and private infrastructure identifiers.

## Live AI26 validation

After preflight/service start, validate from the dashboard and sanitized diagnostics:

1. the active project is `ai26`;
2. canonical MongoDB collections resolve through the shared namespace helpers;
3. a bounded page/aggregate of current collected records is visible;
4. current analysis results are visible;
5. periodic reports appear when present;
6. GraphProjection/DNA/RDF panels degrade cleanly when a capability is absent;
7. Redis worker/status information is project-scoped and transient;
8. RAG/chat uses the existing upstream service/message contract;
9. configuration controls expose only explicitly mutable non-secret fields;
10. restarting the dashboard does not lose durable research state;
11. startup does not require loading the whole corpus;
12. no image/video/audio objects are fetched merely for dashboard rendering.

For interruption testing, stop only services you are authorized to interrupt or use an isolated/reversible connectivity test. The dashboard should recover after MongoDB/Redis connectivity returns; a Redis status outage must not turn Redis into a substitute data store.

## Private access

The public-safe default is `127.0.0.1:8501`. Use the existing Laskin access pattern, such as an SSH tunnel or already protected reverse proxy/private subnet. A simple operator tunnel from a trusted workstation is typically:

```bash
ssh -L 8501:127.0.0.1:8501 <laskin-host>
```

Then browse to the local forwarded port. Host names and account names belong in private/local documentation if they are sensitive.

## Update procedure

```bash
cd /mnt/workspace/LaclauGPT-Data-Visualization
git status --short
git pull --ff-only
.venv/bin/pip install -e '.[remote]'
bash deploy/preflight-laskin-ai26.sh
sudo systemctl restart laclaugpt-visualization-ai26.service
sudo systemctl status laclaugpt-visualization-ai26.service
```

If preflight fails, do not restart the known-good service merely to force the new checkout live.

## Rollback/recovery

Keep the previous known-good Git commit SHA in the private operator notes or deployment state. For a code rollback, stop the service, restore the known-good commit using the team's normal Git workflow, reinstall the editable package if dependencies changed, run preflight, then restart. Do not roll back or delete MongoDB/Redis/Allas data as part of a Visualization code rollback.

If Redis is unavailable, durable MongoDB-backed views should remain conceptually authoritative while transient status/config/messaging features report degradation. If MongoDB is unavailable, report the backend failure clearly rather than silently presenting stale local data as current AI26 state.

## Troubleshooting

- `health` fails before start: inspect its sanitized error class and verify the private environment points at the current shared AI26 services.
- Wrong project/namespace: fix the private environment; never compensate by creating a new visualization database.
- Permission error under the public checkout: runtime writes should point into the private runtime directory, not the public repository.
- Port unavailable: identify the existing process before changing the standard port.
- Public/wildcard bind detected: restore loopback/private-network binding unless an existing protected access layer explicitly requires otherwise.
- Optional RAG/RDF/Hermes unavailable: the dashboard should surface the capability as unavailable/degraded, not fail the core corpus browser.

## Acceptance record

Record live validation results in private deployment notes. Public issue/PR comments may state pass/fail and sanitized counts, versions or commit SHAs, but must not contain credentials, private endpoints, codebooks, research rows or sensitive provenance paths.
