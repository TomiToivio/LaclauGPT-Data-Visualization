# EP24 FI/PL/PT dashboard as an isolated service (#215)

Deployment and operations only. The export and the application come from #195; this document says how
the app is run as its own service, what it is allowed to read, and how to tell whether it is actually
serving the data rather than an empty shell.

Deployment state recorded here was **verified on the host**, not inferred from a merged pull request:
unit active, `/_stcore/health` 200, zero tracebacks, row counts reconciled against the export's own
`MANIFEST.json`, and a forced-kill restart observed.

## What runs

`src/laclaugpt_visualization/ep24_reprocessed_app.py`, served by Streamlit from the repository's own
virtualenv, as a **dedicated systemd user service** on its **own port**. The template lives at
`deploy/ep24-fiplpt.service.example`; the deployed unit is host configuration and is deliberately not
committed.

| Concern | Decision |
|---|---|
| Process manager | systemd **user** unit, `Restart=on-failure`, `WantedBy=default.target`, linger enabled |
| Port | chosen after inspecting listeners; never reuse the AI26 or legacy dashboard ports |
| Bind address | **loopback** (`--server.address 127.0.0.1`), never `0.0.0.0` |
| Access | SSH local forward from an authorized workstation (see *Why loopback*) |
| Data | read-only export directory **outside** this repository |
| Interpreter | the repository's own virtualenv, created from the declared dependency floor (Python ≥ 3.11) |
| Runtime dependencies | Streamlit, pandas, plotly, networkx and the export files. **No MongoDB, Redis, Ollama or GPU at dashboard runtime** |
| Secrets | none in the unit, none in this repository. The dashboard reads files, not services |
| Logs | appended to a log directory outside the repository |

Isolation is the point: this service shares nothing with AI26 except the Python interpreter it is
started from, so restarting or breaking one cannot take the other down.

## Why loopback, and not a public port

The host's provider firewall admits no port that is not already occupied by an existing service:
a listener on any fresh port answers `curl` on the host itself and times out from outside. Opening one
is a firewall change with an owner decision attached, so it is **not** part of this deployment.

The service therefore binds loopback and authorized users reach it with a local forward:

```bash
ssh -N -L 8511:127.0.0.1:8511 <host-alias>
# then browse http://127.0.0.1:8511/ locally
```

This also means there is no unauthenticated public route to the research data while TLS/DNS/
authentication policy is undecided.

## Install

```bash
install -d "$LOG_DIR"
cp deploy/ep24-fiplpt.service.example ~/.config/systemd/user/ep24-fiplpt.service   # substitute paths/port
systemctl --user daemon-reload
sudo loginctl enable-linger "$USER"        # otherwise the unit dies with the last login session
systemctl --user enable --now ep24-fiplpt.service
```

`loginctl enable-linger` is not optional: without it the unit is `active` while the SSH session that
started it lives, and silently `inactive` — or absent — after logout or reboot.

## Verifying it is really serving the export

A healthy process is not the same claim as a correct dashboard. The checks that matter, in order:

1. **Health endpoint** — `/_stcore/health` returns `ok`.
2. **No load errors** — the service log contains no traceback on startup, and the rendered page
   contains no `stException` element.
3. **Row counts reconcile** — `combined.csv` must equal the sum of the country files, and the app's
   header must print the same per-country totals the manifest reports. Verified: 2,125 (FI) +
   1,781 (PL) + 960 (PT) = **4,866** exported video records.
4. **Manifest agreement** — `MANIFEST.json` carries per-country `dna_statements`, `entities`, `sna` and
   `themes`. The dashboard must report these as coverage, and must **show incomplete stages rather than
   hide them**.
5. **Restart survival** — `kill -9` the service `MainPID`, then confirm a *new* PID is `active` and the
   health endpoint answers again. `Restart=on-failure` is a claim until this is observed.

## Known incompleteness (must stay visible in the UI)

The authorized export is genuinely partial, and the dashboard is expected to say so:

| Country | DNA statements | Entities | SNA | Themes |
|---|---|---|---|---|
| Finland | 1,583 | 1,302 | 3,359 | 1,460 |
| Poland | **0** | 1,268 | **0** | 1,440 |
| Portugal | 4 | 1,564 | **0** | 1,507 |

A dashboard that renders Poland's SNA page as an empty chart without saying why is worse than one that
refuses to render it. The incomplete-stage indicator is a requirement, not a nicety.

Observed behaviour on the deployed export: selecting Poland or Portugal and opening *Social network ·
Step 8* renders **"No exported evidence available for this view."** — a refusal, not an empty chart.
Their stage coverage rows read `unavailable in this source`, never `0 %`.

## Two defects this deployment surfaced, and their status

1. **Country keys were read in the wrong shape.** The export keys `record_counts` by full country name
   (`finland`/`poland`/`portugal`); the app looked them up by ISO code (`fi`/`pl`/`pt`). On a complete
   4,866-record corpus it therefore warned *"Countries not represented by this export: fi, pl, pt"* —
   a standing false incomplete-stage indicator on the one page that has to be trustworthy about
   incompleteness. Fixed in `ep24_reprocessed.missing_countries()` / `exported_counts()`, which accept
   both shapes and treat a manifest without counts as *no evidence* rather than as *zero*.
2. **`networkx` was imported but never declared.** The *Combined multilayer* view raised
   `ModuleNotFoundError` on the server because the import is lazy and the dependency list omitted it.
   Declared in `pyproject.toml`; a test now asserts that every third-party import in the entrypoint is a
   declared dependency.

## Known limitation: the DNA view has no rows on this export

The export ships DNA statements in normalized child tables (`children/<country>_dna_statements.csv`)
and leaves the per-row `dna_statements_json` cell empty. The app reads the row cell, so *DNA · Step 7*
reports "No exported evidence available" for Finland even though the manifest counts 1,583 statements.
The manifest and the stage coverage agree with each other; the **app's input contract** is what does not
match the export.

This is not a deployment fault and is not papered over here: wiring the DNA view to the child tables is
a data-contract change tracked as its own issue. Until then, treat the DNA view as unavailable on this
export, and read statements from the child table.

## Redeploy after a merge

The deployed checkout is a **detached** checkout of `origin/main`, never a development branch:

```bash
cd "$VIS_REPO"
echo "ROLLBACK_SHA=$(git rev-parse HEAD)"        # capture before the pull
git fetch origin main
git switch --detach origin/main                 # fast-forward state, no local commits
git status --porcelain | wc -l                  # must be 0
"$VIS_REPO/.venv/bin/python" -m pip install -e . --quiet   # only needed when dependencies changed
systemctl --user restart ep24-fiplpt.service
curl -fsS "http://${BIND_ADDR:-127.0.0.1}:${PORT:-<port>}/_stcore/health"  # expects: ok
```

If the tree is dirty, stop: someone left work in the deployed checkout, and that is a decision, not an
obstacle to route around.

## Data refresh (no redeploy)

The app applies no `st.cache_data`/`st.cache_resource` decorators, so every rerun re-reads the export
from disk. A refresh is therefore a **data** swap, not a code deploy:

```bash
# 1. build the new export into a sibling directory, validated by its own manifest
# 2. verify: row reconciliation from the new MANIFEST.json, sha256 of combined.csv against the manifest
# 3. swap atomically, keeping the previous directory for rollback
mv "$VIS_DATA_DIR" "$VIS_DATA_DIR.prev" && mv "$VIS_DATA_DIR.new" "$VIS_DATA_DIR"
systemctl --user restart ep24-fiplpt.service      # deterministic: clears session state and open files
curl -fsS http://127.0.0.1:8511/_stcore/health    # expects: ok
```

Never write the export in place under a running service: a partially written `combined.csv` renders as a
short corpus that looks like a data loss.

## Rollback

| Rolled back | Command | Effect |
|---|---|---|
| Code | `git switch --detach <previous-commit>` then `systemctl --user restart ep24-fiplpt.service` | previous application, same data |
| Data | `mv "$VIS_DATA_DIR" ...bad && mv "$VIS_DATA_DIR.prev" "$VIS_DATA_DIR"` + restart | previous export, same code |
| Service | `systemctl --user disable --now ep24-fiplpt.service` | stops this service only; AI26 and the legacy dashboards are untouched |

## Not covered here

TLS, DNS, authentication and any reverse-proxy exposure decisions are operational policy, not code.
Until they are decided, the service binds loopback only and is reached through an SSH local forward.
Those remain open on #215.
