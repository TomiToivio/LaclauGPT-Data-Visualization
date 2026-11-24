# Legacy EP24 Merge Lab

The researcher-facing review board for merging labels that mean the same thing (issue #300).
Automatic proposals are computed by `src/laclaugpt_visualization/legacy_curation.py`; this page is the
drag-and-drop review of them.

## Live deployment

It runs on the presentation host described in the private notes, on a port that host exposes
publicly. Location-specific details — host, address, working directory, credentials path — are
deliberately **not** recorded in this public repository; keep them in the private operations notes.

| | |
| --- | --- |
| Working dir | set by `LACLAUGPT_LEGACY_DIR` |
| Source export | `<working dir>/source.csv`, read-only |
| Auth | set by `LACLAUGPT_AUTH_YAML` (a streamlit-authenticator config) |
| Logs | streamlit's log file beside the working dir |

```bash
cd <checkout>
LACLAUGPT_LEGACY_DIR=<working dir> \
LACLAUGPT_AUTH_YAML=<authenticator config> \
setsid nohup python3 -m streamlit run dashboards/legacy_curation/app.py \
  --server.port <port> --server.headless true --server.address 0.0.0.0 \
  --browser.gatherUsageStats false > legacy_lab.log 2>&1 < /dev/null &
```

## Three things that bit us here

1. **A dashboard port may be firewalled upstream even when the host firewalls nothing.** On the
   deployment host `ufw` was inactive and `iptables` accepted everything, yet only some ports
   answered from the internet. Probe with a throwaway listener before trusting a port; do not
   assume "listening on 0.0.0.0" means reachable.
2. **`/_stcore/health` returning 200 does not mean the page renders.** Streamlit executes the script
   only when a session connects, so the first deployment health-checked clean while a first visitor
   would have hit `No module named 'pydantic_settings'`. Verify with a headless render:
   `AppTest.from_file("dashboards/legacy_curation/app.py").run()`.
3. **The app loads `legacy_curation` by path, not through the package.** Importing
   `laclaugpt_visualization` runs its `__init__`, which pulls in the settings/config stack
   (`pydantic-settings`) that this page never needs and that is not installed on every dashboard
   host.

## Using it

Five tabs, one per category. Cards are drag-and-drop: drag one onto another to propose a merge, or
press Enter to select and `M` to propose (keyboard path). Confirm applies and saves; Keep separate
records an explicit non-merge — both are honoured on the next run via
`<working dir>/decisions.json`, with an append-only `decisions_history.jsonl`.

## Running it locally

```bash
LACLAUGPT_LEGACY_DIR=/path/to/working_dir streamlit run dashboards/legacy_curation/app.py
```

No auth locally (the gate is opt-in), no source modification, no credentials in the browser.
