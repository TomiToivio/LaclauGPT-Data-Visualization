# EP24 FI/PL/PT Streamlit deployment runbook (issue #215)

**Status: configuration prepared, not proof of live deployment.** This isolated
service is for the existing `ep24_reprocessed_app.py` only. The default AI26
app, the older :8501/:8503 sites and any :8502 foreground demo are untouched.

## Data and access gates

1. Obtain authorized server/SSH access and an approved read-only FI/PL/PT
   export from the analysis team. Do not put restricted records or credentials
   in this public repository. Verify permitted audience and retention policy.
2. Confirm `combined.csv` and `MANIFEST.json` come from the same release.
   Inspect manifest source hashes, record counts, stage coverage and failures
   using the exporter QA report. A present file alone does not demonstrate
   that every stage/country has completed.
3. Choose a **free** loopback port (example 18512), a dedicated service user,
   and an approved HTTPS authenticated proxy or SSH/VPN forwarding path.
   Do not publicly open the Streamlit port. Confirm port availability with
   `ss -ltn` and inspect existing services before touching any configuration.

## Install on authorized Linux host

Create a dedicated deployment checkout and Python 3.11+ virtual environment;
pin the repository **commit** for each deployment, and record the dependency
resolution from the environment. Do not run `pip install` on the AI26 environment.

```bash
cd /REPLACE_WITH_CHECKOUT
python3 -m venv .venv
.venv/bin/python -m pip install -e .
# Store under private root with 0600 permissions; do NOT commit this file:
# LACLAUGPT_VIS_ANALYSIS_DATA_DIR=/approved/read-only/ep24/export
# Permissions: service user can read export; must not write source or data.
chmod 600 /REPLACE_WITH_PRIVATE_CONFIG/ep24-reprocessed.env
LACLAUGPT_VIS_ANALYSIS_DATA_DIR=/approved/read-only/ep24/export \
  .venv/bin/python deploy/preflight-ep24-reprocessed.py
```

Replace placeholders in
`deploy/laclaugpt-ep24-reprocessed.service.example` and install the resulting
private unit as `laclaugpt-ep24-reprocessed.service`. Ensure service
user/group and all `ExecStart` paths match the checkout and virtual
environment. In particular, the launch script uses the `streamlit` executable
from `PATH`; provide the venv's bin directory first in a **private** service
environment file, e.g. `PATH=/REPLACE_WITH_CHECKOUT/.venv/bin:/usr/local/bin:/usr/bin:/bin`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now laclaugpt-ep24-reprocessed.service
sudo systemctl status laclaugpt-ep24-reprocessed.service
curl --fail --silent http://127.0.0.1:18512/_stcore/health
sudo journalctl -u laclaugpt-ep24-reprocessed.service -n 100 --no-pager
```

The example unit has restart-on-failure and boot persistence, journal logging,
loopback binding, and basic process isolation. Set operational log retention
in the host's journald policy. Validate that the service can read its private
export under the host's directory and mount permissions. Never copy example
paths literally.

## Acceptance smoke checks

- Authenticated researcher reaches the approved URL; anonymous access is
  rejected by the proxy/VPN policy. Test after a reboot.
- The deployed **commit SHA** is documented. No AI26/legacy service/port changed.
- FI, PL, PT and combined views work with the real export; verify each country
  and total count against the *same* release manifest.
- Review Steps 0–9 coverage and the missing/failed/unavailable cases; check
  multimodal, discourse, DNA, SNA, RDF, evidence drilldown and allowed downloads.
- Check large transcript/network rendering, errors, logs, browser downloads
  and export directory permissions for unintended disclosure.
- Record the health result, deployment revision, export manifest time/hash,
  endpoint (redacted if necessary), and authorized tester in issue #215.

## Refresh and rollback

Never overwrite live CSV files individually. Build a **complete** new export in
a private staging directory, verify all files, counts, stage statuses and source
hashes, then point the private environment file at the new immutable directory
and restart. Only after health and FI/PL/PT smoke checks pass may the old export
be retired under institutional retention rules. Roll back by restoring the
previous verified export path and previous pinned code revision, then restart
and repeat the health and country checks.

A failure of preflight is intentional and must not be bypassed by substituting
synthetic files. Missing server access, approved data, authentication or
institutional permissions blocks completion of issue #215.
