# Legacy EP24 Merge Lab

The researcher-facing review board for merging labels that mean the same thing (issue #300).
Automatic proposals are computed by `src/laclaugpt_visualization/legacy_curation.py`; this page is the
drag-and-drop review of them.

## Live deployment

| | |
| --- | --- |
| URL | http://86.50.228.141:8503/ |
| Host | SpectacleScraper (`/home/ubuntu/LaclauGPT-Data-Visualization`) |
| Working dir | `/home/ubuntu/legacy_lab` (`LACLAUGPT_LEGACY_DIR`) |
| Source export | `/home/ubuntu/legacy_lab/source.csv` → the PLEDGE workbook (12,394 rows) |
| Auth | `LACLAUGPT_AUTH_YAML` → the pledge dashboard's `auth.yaml` (same login, no new secret) |
| Logs | `/tmp/legacy_lab.log` |

```bash
cd ~/LaclauGPT-Data-Visualization
LACLAUGPT_LEGACY_DIR=/home/ubuntu/legacy_lab \
LACLAUGPT_AUTH_YAML=/home/ubuntu/LaclauGPT-Data-Storage/laclaugpt/pledge_dashboard/auth.yaml \
setsid nohup python3.10 -m streamlit run dashboards/legacy_curation/app.py \
  --server.port 8503 --server.headless true --server.address 0.0.0.0 \
  --browser.gatherUsageStats false > /tmp/legacy_lab.log 2>&1 < /dev/null &
```

### Three things that bit us here

1. **Only ports 8501–8503 are reachable from outside.** `ufw` is inactive and `iptables` accepts
   everything, so the filtering is upstream of the host: 8504 and 8100 listen locally and return
   nothing from the internet, while 8503 answers. Do not pick a port above 8503 for a public
   dashboard on this machine.
2. **`/_stcore/health` returning 200 does not mean the page renders.** Streamlit only executes the
   script when a session connects; the first deployment health-checked clean while a first visitor
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
