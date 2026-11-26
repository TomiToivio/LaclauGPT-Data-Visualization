# One AI26 dashboard on Laskin, on `:8504` (#330)

Supersedes the earlier `:8501` canonical policy and every older Laskin dashboard note. There is now
exactly one dashboard on Laskin, the AI26 research dashboard, and it serves on
`http://<private-host>:8504/`. No Streamlit password gate: access is restricted outside Streamlit
(the service binds the host's private address only).

## Deployed state (2026-11-26)

| port | before | after |
| --- | --- | --- |
| 8501 | AI26 dashboard (`ai26_dashboard.py`) | **retired** |
| 8502 | EP24 FI/PL/PT researcher (`laclaugpt-ep24-researcher`) | **retired** |
| 8503 | EP24 live steps 1–7 (`laclaugpt-live-steps`) | **retired** |
| 8504 | EP24 Merge Lab (`dashboards/ep24_merge_lab/ui/app.py`) | **AI26 dashboard** |

Units stopped and disabled: `laclaugpt-ep24-researcher`, `laclaugpt-live-steps`, `ep24-fiplpt`,
`laclaugpt-visualization-ai26` (it had re-bound `:8501`), `laclaugpt-ep24-mongo-demo`,
`laclaugpt-ep24-demo`, `ep24-workbench-laskin`, `laclaugpt-ep24-merge-lab`, and the old
`ai26-dashboard` unit that pointed at an unrelated CLI on `:8502`.

Untouched: `ai26-capture`, `ai26-backup.timer`, `ai26-export.timer`, `brazil-capture` and every
research-data repository on the host. The external EP24 reference dashboards
(on their separate host) are not affected.

## The service template

`deploy/laskin/ai26-dashboard.service` (installed at `~/.config/systemd/user/`):

* `WorkingDirectory=%h/LaclauGPT-Data-Visualization`, a checkout of `main`; override both WorkingDirectory and ExecStart in a local systemd drop-in if the checkout is elsewhere;
* the updated template runs preflight and then `laclaugpt-visualize serve` on the configured tailnet bind;
* configuration comes from `~/.config/laclaugpt/ai26/dashboard.env` (mode 600). It holds the
  `LACLAUGPT_VIS_*` and `LACLAUGPT_REDIS_URL` values the previous dashboard ran with, with
  `LACLAUGPT_VIS_SERVER_PORT=8504` and `LACLAUGPT_VIS_SERVER_HOST` set to the private host address. Set the reviewed full `LACLAUGPT_VIS_RELEASE_SHA` and verified `LACLAUGPT_VIS_NETWORK_ACCESS_VERIFIED=1` there before restarting. Secrets stay in that file and never in this repository;
* `Restart=on-failure`, `WantedBy=default.target`; the user has `Linger=yes`, so it survives logout
  and reboot.

The dashboard loads canonical AI26 records; it does not start analysis on load and needs no Allas
download for display.

## Verification reported by the original deployment operator

```
ss -ltnp | grep :85            -> one listener: <private-host>:8504
curl :8504/_stcore/health      -> 200
systemctl --user list-unit-files --state=enabled | grep -i dash
                               -> ai26-dashboard.service  (only)
AppTest.from_file(".../ai26_dashboard.py").run()   # on Laskin, service env loaded
                               -> no exception; title "LaclauGPT · AI26 Research Dashboard";
                                  24 markdown blocks, 8 dataframes, 9 tabs rendered from real data
```

## Rollback

Follow the [canonical runbook](AI26_LASKIN_DASHBOARD.md): stop the single AI26 unit and restore only a previously verified consolidated release, its dependencies and protected configuration. Do not re-enable retired EP24 or other dashboards. If no consolidated release is available, leave the service stopped.

## Still open under #330

This document covers the deployment half only. The researcher-first overview, the NoöPunk design
system, and the NetworkX + D3 multilayer DA/DNA/SNA explorer are still to be built on top of this
single, now-verified deployment target.
