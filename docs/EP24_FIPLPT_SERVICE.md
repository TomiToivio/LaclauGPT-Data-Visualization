# EP24 FI/PL/PT dashboard as an isolated service (#215)

Deployment and operations only. The export and the application come from #195; this document says how
the app is run as its own service, what it is allowed to read, and how to tell whether it is actually
serving the data rather than an empty shell.

## What runs

`src/laclaugpt_visualization/ep24_reprocessed_app.py`, served by Streamlit from the repository's own
virtualenv, as a **dedicated systemd user service** on its **own port**. The template lives at
`deploy/ep24-fiplpt.service.example`; the deployed unit is host configuration and is deliberately not
committed.

| Concern | Decision |
|---|---|
| Process manager | systemd **user** unit, `Restart=on-failure`, `WantedBy=default.target`, linger enabled |
| Port | chosen after inspecting listeners; never reuse the AI26 (`:8501`) or legacy (`:8503`) ports |
| Bind address | the host's private interface, never `0.0.0.0` |
| Data | read-only export directory **outside** this repository |
| Runtime dependencies | Streamlit and the export files. **No MongoDB, Redis, Ollama or GPU at dashboard runtime** |
| Secrets | none in the unit, none in this repository. The dashboard reads files, not services |
| Logs | appended to a log directory outside the repository |

Isolation is the point: this service shares nothing with AI26 except the Python interpreter it is
started from, so restarting or breaking one cannot take the other down.

## Verifying it is really serving the export

A healthy process is not the same claim as a correct dashboard. The checks that matter:

1. **Health endpoint** — `/_stcore/health` returns `ok`.
2. **No load errors** — the service log contains no traceback on startup.
3. **Row counts reconcile** — `combined.csv` must equal the sum of the country files. At the time of
   writing: 49,003 (FI) + 46,949 (PL) + 26,309 (PT) = **122,261** combined rows.
4. **Manifest agreement** — `MANIFEST.json` carries per-country `dna_statements`, `entities`, `sna` and
   `themes`. The dashboard must report these as coverage, and must **show incomplete stages rather than
   hide them**.

## Known incompleteness (must stay visible in the UI)

The authorized export is genuinely partial, and the dashboard is expected to say so:

| Country | DNA statements | Entities | SNA | Themes |
|---|---|---|---|---|
| Finland | 1,583 | 1,302 | 3,359 | 1,460 |
| Poland | **0** | 1,268 | **0** | 1,440 |
| Portugal | 4 | 1,564 | **0** | 1,507 |

A dashboard that renders Poland's SNA page as an empty chart without saying why is worse than one that
refuses to render it. The incomplete-stage indicator is a requirement, not a nicety.

## Access decision: tailnet-only, no public route

The service binds a **private interface address**, not `0.0.0.0`, and there is deliberately **no public
DNS name, no TLS terminator and no password layer** in front of it. This is the decision, not an
unfinished item:

| Concern | Decision | Why |
|---|---|---|
| Transport encryption | WireGuard, via the tailnet | the interface is only reachable inside the encrypted mesh |
| Authentication | device identity on the tailnet | only enrolled machines can open the socket at all |
| Public exposure | none | the export is restricted research data; no route exists to it from the internet |
| Password prompt | none | a second password over an already device-authenticated mesh adds support burden, not security |

If the audience ever has to include someone outside the tailnet, that is a **new decision** requiring a
reverse proxy with authentication, a certificate, and a written access list — not a port opening. Record
it here before doing it.

## Restart, crash and rollback

Verified on the host (2026-10-31):

```
systemctl --user restart ep24-fiplpt.service      # pid changed, health 200 after ~8 s
kill -9 <MainPID>                                 # Restart=on-failure brought it back
                                                  # active, new pid, health 200
systemctl --user is-enabled ep24-fiplpt.service   # enabled
```

Rollback of a **code** deployment is `git checkout <known-good-commit>` then
`systemctl --user restart ep24-fiplpt.service`. Rollback of a **data** refresh is swapping the export
directory back (see the refresh procedure) — the two are separate operations on purpose, so a bad
export never requires a code rollback and vice versa.

## Smoke test

`scripts/ep24/smoke_ep24_dashboard.py` drives the real app with Streamlit's `AppTest` against the
deployed export and reconciles what the UI shows with `MANIFEST.json`:

```bash
LACLAUGPT_VIS_ANALYSIS_DATA_DIR=<export dir> \
  .venv/bin/python scripts/ep24/smoke_ep24_dashboard.py
```

Last run against `mongo_export_210` — **12 checks, 0 failures**:

```
OK: EP24 dashboard served 4866 records (finland 2125, poland 1781, portugal 960)
```

It asserts the title, that the manifest caption is present, that the country selector offers all three
countries **with their manifest counts**, that the corpus total matches, and that each country scope
renders without an exception. A dashboard that starts but silently shows an empty frame passes
`/_stcore/health` and fails this.

## Not covered here

TLS, DNS, authentication and reverse-proxy exposure are operational policy and are decided above:
**the service is tailnet-only**. Anything beyond that is a new decision, not a remaining task.
