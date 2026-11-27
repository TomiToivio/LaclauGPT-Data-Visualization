# AI26 dashboard handover: a copy Jeeves can run (issue #342)

This is the Laskin side of the handover. It records what the development service actually runs,
what a copy needs, and how to produce the one artefact a public copy is allowed to read. The
private dashboard stays the authoritative research surface; the public one is a copy that reads a
versioned bundle and nothing else.

## 1. Verified development deployment (Laskin, 2026-11-27)

| Item | Verified value |
| --- | --- |
| Host / endpoint | The Laskin development host (`laskin01`), on its Tailnet address and port 8504 — private network only, never public |
| Repository | `TomiToivio/LaclauGPT-Data-Visualization`, private checkout on the host (path withheld) |
| Branch / served commit | `main` @ `61f0559` (verified in the served checkout; the page footer also prints the revision it first rendered) |
| Entrypoint | `src/laclaugpt_visualization/ai26_dashboard.py` (`streamlit run`) |
| Start command | `.venv/bin/python -m streamlit run src/laclaugpt_visualization/ai26_dashboard.py --server.address <host> --server.port 8504 --server.headless true` |
| Service manager | user unit `ai26-dashboard.service`, `Restart=on-failure`, `RestartSec=20` |
| Environment file | A private unit environment file outside the repository, mode-protected (path withheld) |
| Python / UI stack | Python 3.11.14, Streamlit 1.67.0, plotly, pandas; dependencies declared in `pyproject.toml` (no lockfile — pin a commit instead) |
| Data source | MongoDB (private endpoint, set by `LACLAUGPT_VIS_MONGODB_URI` / `LACLAUGPT_VIS_MONGODB_DATABASE`), collections `ai26__records`, `ai26__analysis_results`, and `kg_meta`/`kg_nodes`/`kg_edges` for the DNA/SNA layers |
| Refresh | manual: sidebar **Refresh now**; no background polling |
| Authentication | none configured on Laskin; the boundary is the Tailnet bind, so a public copy needs its own access control |
| Health | `GET /_stcore/health` → `200` |

Configuration **names** the service uses (values never leave the host):
`LACLAUGPT_VIS_PROFILE`, `_MACHINE`, `_EXECUTION`, `_STORAGE`, `_PROJECT_ID`,
`_BROWSER_DATA_CONTRACT`, `_CALLER`, `_STORAGE_BACKEND`, `_DATA_BACKEND`, `_CACHE_BACKEND`,
`_MESSAGING_BACKEND`, `_OBJECT_BACKEND`, `_SERVER_HOST`, `_SERVER_PORT`, `_DATA_DIR`, `_OUTPUT_DIR`,
`_REDIS_KEY_PREFIX`, `_S3_PREFIX_ROOT`, `_MONGODB_URI`, `_MONGODB_DATABASE`, plus
`LACLAUGPT_REDIS_URL` and the `LACLAUGPT_VIS_S3_*` family.

## 2. What a public copy must not have

The research dashboard reads a private database and offers views that query live services. A copy
therefore:

- runs with **no** Mongo, Redis or S3 configuration at all — a demo never falls back to a private
  endpoint, and if the bundle is missing it says so instead of connecting anywhere;
- renders only **Explore, Networks and Records**, which are read-only views over the bundle
  (`DEMO_TABS` in `ai26_dashboard.py`);
- does not build the Reports, RAG Chat, Configuration, Hermes or Diagnostics tabs, because those
  read services, write review state, or expose host configuration;
- shows a banner naming the data as a demonstration with an explicit as-of timestamp.

## 3. Producing the bundle

```bash
# 1. Synthetic first: proves the packaging and lets the copy be smoke-tested with no real data.
python scripts/export_ai26_demo_bundle.py --output /srv/ai26-demo/releases/<stamp>

# 2. Real data only after the study owner approves the exact scope, and only on the private host.
LACLAUGPT_MONGODB_URI=… LACLAUGPT_MONGODB_DATABASE=… \
python scripts/export_ai26_demo_bundle.py --from-mongo --approve-scope \
  --output /srv/ai26-demo/releases/<stamp> --graph /path/to/kg-export.json --as-of <ISO timestamp>
```

The bundle is `records.jsonl` + optional `graph.json` + `manifest.json` + `README.md`.
`manifest.json` carries the record count, the data-as-of stamp, the code revision and a sha256 per
file, so a copy can be verified rather than trusted.

The allowlist is the privacy boundary, enforced in code and covered by tests: a bundle never
contains raw capture payloads, provenance internals, review state, native ids, database ids,
media references, endpoints or credentials. `source_url` and the timestamps are kept, because
without them nothing on the dashboard can be dated or traced.

## 4. Running a copy (Jeeves)

```bash
git clone https://github.com/TomiToivio/LaclauGPT-Data-Visualization.git
cd LaclauGPT-Data-Visualization
git checkout <release commit>            # pin the revision the bundle was exported from
python3.11 -m venv .venv && .venv/bin/python -m pip install -e .
```

Systemd unit shape (public host, bound to loopback behind a TLS reverse proxy):

```ini
[Service]
WorkingDirectory=/srv/ai26-demo/app
Environment=LACLAUGPT_VIS_DEMO_MODE=1
Environment=LACLAUGPT_VIS_DEMO_BUNDLE=/srv/ai26-demo/current/records.jsonl
Environment=LACLAUGPT_VIS_DEMO_GRAPH=/srv/ai26-demo/current/graph.json
Environment=LACLAUGPT_VIS_DEMO_AS_OF=<data-as-of from manifest.json>
ExecStart=/srv/ai26-demo/app/.venv/bin/python -m streamlit run \
  src/laclaugpt_visualization/ai26_dashboard.py \
  --server.address 127.0.0.1 --server.port 8504 --server.headless true
Restart=on-failure
```

`LACLAUGPT_VIS_DEMO_MODE` defaults to off, so the same code runs unchanged on Laskin.

## 5. Daily update, verification and rollback

1. Pull the release: a tested commit of this repository plus a freshly exported bundle.
2. Verify the bundle against its manifest (`sha256sum -c`, or the checksums in `manifest.json`).
3. Stage it as `/srv/ai26-demo/releases/<stamp>/` and switch `/srv/ai26-demo/current` to it
   atomically (`ln -sfn`), then restart the unit.
4. Smoke test: `curl -fsS localhost:8504/_stcore/health`, then load the page and confirm the
   banner's as-of stamp and the record count changed together.
5. Keep the previous release directory; rollback is switching `current` back and restarting.
6. Never pull private directories, databases, credentials or unreviewed records; never write back
   to Laskin.

## 6. What is still open on this issue

- The demo data scope needs Tomi's approval before any real records are exported; until then the
  synthetic bundle is the only one that may be published.
- Jeeves owns the public host, TLS, hardening and the daily job; this document describes the copy,
  not that deployment.
- The DNA/SNA layers appear in the demo only when the bundle includes a `graph.json` produced by
  Data Analysis; without it the copy honestly reports zero edges for those layers.
