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

## Not covered here

TLS, DNS, authentication and any reverse-proxy exposure decisions are operational policy, not code. Until
they are decided, the service binds a private interface only. Those remain open on #215.
