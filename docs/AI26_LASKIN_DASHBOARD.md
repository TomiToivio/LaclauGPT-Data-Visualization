# AI26 dashboard on Laskin

This is the public, secret-free Phase 1 deployment runbook for the AI26 visualization service on Laskin. The deployment uses the unified Visualization application and the canonical Collection → Analysis → Visualization contract. It does not fork analysis logic or embed private AI26 settings in this repository.

## Phase 1 contract

- `main` is the canonical active/stable Phase 1 development branch.
- `phase-1` is a passive mirror and must match the validated `main` tree.
- Select AI26 explicitly with `LACLAUGPT_VIS_PROJECT_ID=ai26`.
- Select the canonical Phase 1 browser contract with `LACLAUGPT_VIS_BROWSER_DATA_CONTRACT=canonical`.
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

It verifies AI26 selection, the canonical Phase 1 contract, Linux web-service execution, safe binding, retirement of obsolete legacy services, and then runs the sanitized application commands:

```bash
.venv/bin/laclaugpt-visualize profile
.venv/bin/laclaugpt-visualize health
```

`profile` and `health` both expose the effective non-secret `browser_data_contract`, so an operator can verify that the running service selected `canonical` without printing credentials. Optional capability failures must be shown as unavailable/degraded rather than causing unrelated views to crash.

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

The legacy JSONL dashboard/export path from the former monolithic deployment is not part of the supported Phase 1 visualization service. Before enabling the unified service, retire those units if present:

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

## Update and restart

```bash
cd "$LACLAUGPT_VIS_REPO_ROOT"
git status --short
git pull --ff-only
.venv/bin/pip install -e '.[remote]'
bash deploy/preflight-laskin-ai26.sh
sudo systemctl restart laclaugpt-visualization-ai26.service
sudo systemctl status laclaugpt-visualization-ai26.service
```

If preflight fails, leave the known-good service in place and fix the configuration or checkout before restarting.

## Logs and privacy

Use the service manager journal for process logs. Do not paste logs into public issues without checking for research content, private endpoints, credentials or private provenance paths. Runtime data and researcher notes must remain under the configured private runtime root, never inside the public Git checkout.
