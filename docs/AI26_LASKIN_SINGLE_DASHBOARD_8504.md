# One AI26 dashboard on Laskin, on `:8504` (#330)

Supersedes the earlier `:8501` canonical policy and every older Laskin dashboard note. There is now
exactly one dashboard on Laskin, the AI26 research dashboard, and it serves on
`http://100.115.95.109:8504/`. No Streamlit password gate: access is restricted outside Streamlit
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
(`195.148.31.227:8501/8502`) are not affected.

## The service

`deploy/laskin/ai26-dashboard.service` (installed at `~/.config/systemd/user/`):

* `WorkingDirectory=/mnt/workspace/LaclauGPT-Data-Visualization`, a checkout of `main`;
* `ExecStart` runs `streamlit run src/laclaugpt_visualization/ai26_dashboard.py` on
  `--server.address 100.115.95.109 --server.port 8504`;
* configuration comes from `~/.config/laclaugpt/ai26/dashboard.env` (mode 600). It holds the
  `LACLAUGPT_VIS_*` and `LACLAUGPT_REDIS_URL` values the previous dashboard ran with, with
  `LACLAUGPT_VIS_SERVER_PORT=8504`. Secrets stay in that file and never in this repository;
* `Restart=on-failure`, `WantedBy=default.target`; the user has `Linger=yes`, so it survives logout
  and reboot.

The dashboard loads canonical AI26 records; it does not start analysis on load and needs no Allas
download for display.

## Verification performed

```
ss -ltnp | grep :85            -> one listener: 100.115.95.109:8504
curl :8504/_stcore/health      -> 200
systemctl --user list-unit-files --state=enabled | grep -i dash
                               -> ai26-dashboard.service  (only)
AppTest.from_file(".../ai26_dashboard.py").run()   # on Laskin, service env loaded
                               -> no exception; title "LaclauGPT · AI26 Research Dashboard";
                                  24 markdown blocks, 8 dataframes, 9 tabs rendered from real data
```

## Rollback

```bash
systemctl --user disable --now ai26-dashboard
systemctl --user enable --now laclaugpt-ep24-merge-lab   # the previous :8504 occupant
# and, only if the old topology is genuinely needed:
systemctl --user enable --now laclaugpt-ep24-researcher laclaugpt-live-steps
```

The retired units and their files are intact; nothing was deleted, so the previous topology is one
`enable --now` away.

## Still open under #330

This document covers the deployment half only. The researcher-first overview, the NoöPunk design
system, and the NetworkX + D3 multilayer DA/DNA/SNA explorer are still to be built on top of this
single, now-verified deployment target.
