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

## 2. Data scope and boundaries

**Jeeves serves the full real-time AI26 dataset** (decision: Tomi, 2026-11-27), read through a
dedicated **read-only** database account. The demo renders only what it can read: it never writes,
never changes review state, and never mutates the store.

**EP24 is permanently out of bounds.** EP24 is an official University of Helsinki project; its
data, services, repositories, exports and review state are governed by university rules and are
not part of this handover. A public copy must not read, copy, mirror, join or publish EP24
material, and must not reuse an EP24 credential, endpoint or export path.

**AI26 is not (yet) an official university project.** It is Tomi's own, so the university rules
that bind EP24 do not apply to it. What still applies is the study's own discipline: no secrets or
endpoints in the repository or in issue text, no media binaries (text-only directive, #450),
respect for each source's terms and the declared sampling frame, and outputs presented as
descriptive observations of a non-official study with the experimental layers labelled.

## 3. What a public copy must not have

The research dashboard reads a private database and offers views that query live services. A copy
therefore:

- renders only **Explore, Networks and Records** (`DEMO_TABS` in `ai26_dashboard.py`);
- does not build the Reports, RAG Chat, Configuration, Hermes or Diagnostics tabs, because those
  read a service, write review state, or expose host configuration;
- names its data source in a banner, with the freshness or as-of stamp, so stale data cannot pass
  for a healthy update;
- never falls back: a live copy with no connection shows the error, and a bundle copy with no
  bundle shows the error, instead of quietly reaching somewhere else.

## 4. Two approved data sources

`LACLAUGPT_VIS_DEMO_SOURCE` picks one, explicitly:

| source | what it reads | when to use |
| --- | --- | --- |
| `live` (primary) | the AI26 store over a read-only account: `ai26__records`, `ai26__analysis_results`, `kg_*` | the real-time public demo Jeeves operates |
| `bundle` (fallback) | a versioned export written by `scripts/export_ai26_demo_bundle.py` | offline copies, scheduled snapshots, smoke tests |

Producing the bundle, when it is used:

```bash
# 1. Synthetic: proves the packaging with no real data at all.
python scripts/export_ai26_demo_bundle.py --output /srv/ai26-demo/releases/<stamp>

# 2. Real data: the scope decision is recorded in issue #342, so the flag documents the approval.
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

## 5. The read-only account (provisioning is not self-service)

The account must be created on the database server by whoever administers it. The application
user the research dashboard uses **cannot** create users (`usersInfo` is refused), so this is not
something a copy can do for itself, and it must not be worked around by handing the demo the
research credentials.

Requirements for the account:

- one database, the AI26 database; no cluster-wide role;
- read-only: `read` on that database only — no `readWrite`, no `dbAdmin`, no `userAdmin`;
- no access to any other database in the instance, in particular nothing EP24-related;
- password rotated independently of the research credentials, and never committed.

A copy proves the grant by reading and by failing: `find` on `ai26__records` succeeds, and a write
attempt is refused. Do that once on the public host before serving traffic.

## 6. Running a copy (Jeeves)

```bash
git clone https://github.com/TomiToivio/LaclauGPT-Data-Visualization.git
cd LaclauGPT-Data-Visualization
git checkout <release commit>            # pin the revision you deploy
python3.11 -m venv .venv && .venv/bin/python -m pip install -e .
```

Systemd unit shape for the **live** demo (public host, bound to loopback behind a TLS reverse
proxy). The account is the read-only one from §5; nothing else in the environment:

```ini
[Service]
WorkingDirectory=/srv/ai26-demo/app
Environment=LACLAUGPT_VIS_DEMO_MODE=1
Environment=LACLAUGPT_VIS_DEMO_SOURCE=live
Environment=LACLAUGPT_VIS_PROJECT_ID=ai26
Environment=LACLAUGPT_VIS_MONGODB_URI=<read-only account connection string, from the 0600 env file>
Environment=LACLAUGPT_VIS_MONGODB_DATABASE=<ai26-db>
ExecStart=/srv/ai26-demo/app/.venv/bin/python -m streamlit run \
  src/laclaugpt_visualization/ai26_dashboard.py \
  --server.address 127.0.0.1 --server.port 8504 --server.headless true
Restart=on-failure
```

Keep the URI in a mode-0600 environment file rather than inline in the unit, as the Laskin service
does. No Redis, S3 or EP24 variable belongs in a demo environment.

`LACLAUGPT_VIS_DEMO_MODE` defaults to off, so the same code runs unchanged on Laskin.

## 7. Daily operation, verification and rollback

Live mode needs no data transfer: the copy reads the store on every rerun, so "synchronization" is
the repository release plus a restart.

1. Deploy a tested commit (see the release procedure in this repository's README).
2. Restart the unit, then `curl -fsS localhost:8504/_stcore/health`.
3. Load the page and read the banner: record count and newest-analysis timestamp must be current.
   A stale stamp with a healthy service means the read is failing quietly — investigate, do not
   assume the store is empty.
4. Keep the previous release directory; rollback is checking out the previous commit, reinstalling
   if the dependency set changed, and restarting.
5. Read-only proof, once per deployment and after any credential rotation: `find` succeeds on
   `ai26__records`, a write attempt is refused.
6. Never pull private directories, databases or unreviewed records; never write back
   to Laskin.

## 7b. The operational pieces a demo host installs (snapshot/bundle path)

For the bundle source (`LACLAUGPT_VIS_DEMO_SOURCE=bundle`), two files turn the runbook into
something a host can own rather than retype:

* `deploy/laclaugpt-visualization-public-demo.service.example` — the demo unit. It pins
  `LACLAUGPT_VIS_DEMO_MODE=true`, reads `<demo-root>/current/records.jsonl`, binds `127.0.0.1:8600`
  and carries no database, cache or object-store variables at all, so the copy cannot reach a
  private endpoint even by mistake.
* `scripts/update_ai26_demo_release.sh` — the daily switch. It verifies every checksum in
  `manifest.json` **before** writing, stages `releases/<stamp>/`, moves the `current` symlink
  atomically, restarts the unit, waits for `/_stcore/health`, and rolls the symlink back to the
  previous release when health does not come up. `--dry-run` verifies and prints the plan without
  touching the filesystem or the service.

```bash
# stage and switch, rollback automatic on failure
scripts/update_ai26_demo_release.sh \
  --bundle /srv/ai26-demo/incoming --root /srv/ai26-demo \
  --service ai26-demo.service --health-url http://127.0.0.1:8600/_stcore/health

# verify-only, safe to run in a monitoring job
scripts/update_ai26_demo_release.sh --bundle /srv/ai26-demo/incoming --root /srv/ai26-demo --dry-run
```

A tampered bundle never reaches `current`: the checksum check runs first and exits non-zero with
the offending file named. The record count and the data-as-of stamp in the banner come from the
same manifest, so a visitor always sees which snapshot is live.

## 8. What is still open

- **The read-only account must be provisioned on the database server** by its administrator (see
  §5). The research credentials cannot create it and must not be shipped to the public host.
- Jeeves owns the public host, TLS, hardening and the restart procedure; this document describes
  the copy, not that deployment.
- In live mode the DNA/SNA layers come from the published `kg_*` graph, so they track whatever Data
  Analysis has projected; when no graph is published the copy reports zero rather than inferring.
- The demo unit and release switch in §5b assume the bundle source. A live demo needs neither the
  bundle nor the switch: it reads the store on each rerun, so a release is a code deploy plus a
  restart, and freshness is read from the banner rather than from a manifest.
