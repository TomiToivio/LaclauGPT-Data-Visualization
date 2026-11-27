# Making a copy of the AI26 dashboard for a public demo (#342)

The Laskin service at `http://100.115.95.109:8504/` stays the authoritative private development
dashboard. This document describes the **copy**: a separate deployment of the same maintained
code against an approved, read-only demo dataset, on a host that never needs inbound access to
Laskin or the private research database.

## What a copy is, and what it is not

| | Private development dashboard | Public demo copy |
| --- | --- | --- |
| Code | this repository, `main` | the **same** repository at a released commit — no fork |
| Data | live AI26 corpus, private | approved snapshot, synthetic fixture until Tomi approves a scope |
| Bind | private address, network-level access control | loopback behind a reverse proxy with HTTPS |
| Surfaced tabs | all nine | Monitor, Explore, Networks, Reports (`LACLAUGPT_VIS_DEMO_MODE=true`) |
| Writes | none, but reads Redis configuration | none at all: no Redis, no S3, read-only Mongo user |

## 1. Install the copy

```bash
git clone https://github.com/TomiToivio/LaclauGPT-Data-Visualization.git "$DEMO_ROOT"
cd "$DEMO_ROOT"
git checkout <released-commit>
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
# The dashboard's live data path needs the remote extras; the demo still only reads.
.venv/bin/python -m pip install -e '.[remote]'
```

Record the installed commit. A copy that cannot name its revision cannot be rolled back:

```bash
git -C "$DEMO_ROOT" rev-parse HEAD
```

## 2. Configure it

Start from [`deploy/public-demo.env.example`](../deploy/public-demo.env.example) and keep the
filled file private (mode 0600, outside the repository). The names it sets are the contract; the
values are per-host.

Two settings decide the public surface:

* `LACLAUGPT_VIS_DEMO_MODE=true` removes the Records, RAG Chat, Configuration, Hermes and
  Diagnostics tabs. They are not registered at all, so no URL, query or widget reaches raw corpus
  text, model access over the private corpus, effective configuration or agent operations.
* `LACLAUGPT_VIS_DEMO_DATA_LABEL` is printed verbatim in the banner. It must say what the visitor
  is looking at (`synthetic fixture`, `approved snapshot 2026-11-27, AI26, n=1200`); it must not
  carry record text or personal data.

`LACLAUGPT_VIS_SERVER_HOST=127.0.0.1` keeps Streamlit off the public interface; the reverse proxy
terminates TLS.

## 3. Provide the data

The dashboard performs live queries (`load_ai26_snapshot`), so a copy needs a MongoDB holding the
approved demo scope. Two acceptable sources:

1. **Synthetic fixture** (default until Tomi approves a data scope). Build a small database with
   the same collection names and the canonical record/analysis shape.
2. **Approved snapshot.** Tomi approves the scope in writing in issue #342; then export a bounded,
   sanitised subset on Laskin and restore it on the demo host. Export and restore stay inside the
   private boundary: no raw capture payloads, no evidence quotes beyond the approved scope, no
   private source lists, and no copy of the production database.

Collections the dashboard reads (names are configuration, not secrets):

| collection | content |
| --- | --- |
| `ai26__records` | canonical records, one per `source_url` |
| `ai26__analysis_results` | analysis results keyed by the same `source_url` |
| `ai26__processing` | in-flight/failed analysis rows, shown only as failure counts |
| `kg_meta`, `kg_nodes`, `kg_edges` | the AnalyticalGraph the Networks tab reads (DA/DNA/SNA layers) |

Give the demo user `read` on the demo database only.

## 4. Serve it

```bash
cp deploy/laclaugpt-visualization-public-demo.service.example \
   ~/.config/systemd/user/ai26-demo.service
# replace <demo-root>, <demo-env-file>, <demo-user>/<demo-group>, <demo-runtime-root>
systemctl --user daemon-reload
systemctl --user enable --now ai26-demo.service
systemctl --user status ai26-demo.service --no-pager
```

`laclaugpt-visualize serve` is the supported entrypoint: it binds to the configured host and port
and serves the project's own module, so a copy cannot silently serve the legacy generic workbench
(#44). Readiness without side effects:

```bash
.venv/bin/laclaugpt-visualize health   # exit 0 == ready
.venv/bin/laclaugpt-visualize profile  # effective non-secret settings
```

## 5. Verify acceptance

```bash
curl -fsS http://127.0.0.1:<port>/_stcore/health      # "ok"
curl -fsS https://<public-url>/                       # reverse proxy chain
```

Then in a browser, on the public URL: the demo banner shows the data label; only Monitor, Explore,
Networks and Reports are present; the Networks tab renders DA/DNA/SNA layers or states honestly
that a layer has no validated upstream graph; filters and the source window behave as on Laskin.

Record in issue #342: public URL, deployed commit, data-as-of timestamp, and the tab list observed.

## 6. Update, roll back, report freshness

* **Update**: check out the new released commit, reinstall if dependencies changed, restart, and
  re-run the verification above. Keep the previous commit recorded.
* **Roll back**: check out the last known-good commit, reinstall, restart, verify.
* **Freshness**: the copy is a snapshot, not a live feed. The banner data label plus the deployed
  commit is the honest statement of what a visitor sees. Do not imply continuous analysis.

`deploy/laskin-served-drift.service.example` shows how the development side reports the difference
between the checkout and the process actually serving; the demo host should keep the equivalent
pair (deployed commit vs running process) in its own monitoring.

## 7. Never copy these

Raw capture payloads, credentials or `.env` files from Laskin, SSH keys, private study
configuration, the private database, corpus exports outside the approved scope, or any path under
the development host's private runtime. If a step seems to need one of them, the data scope has not
been approved yet — use the synthetic fixture and ask in issue #342.
