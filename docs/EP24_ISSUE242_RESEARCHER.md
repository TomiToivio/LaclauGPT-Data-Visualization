# EP24 FI/PL/PT Monday500 researcher dashboard (issue #242)

## Working scope

**New, isolated Streamlit entrypoint:** `src/laclaugpt_visualization/ep24_researcher_app.py`.
The AI26 dashboard and the legacy Streamlit services remain unchanged.

Run against the **authorized private, read-only FI/PL/PT Monday500 export** of
`ep24_monday500_20261031`, never silently against `ep2024_reprocess`.
The app checks the manifest/run identifier and reports the precise counts for
FI/PL/PT rather than claiming 500 videos per country without evidence.

The existing canonical exporters (issue #195) generate `combined.csv`,
`MANIFEST.json`, research child tables and bundled evidence. No new incompatible
export format is introduced. Build/update the private snapshot **on an authorized
producer host**, then sync it into the authorized private research area. A GitHub
repository, even private, is not automatically approved for sensitive source media.

## Git-pull run on Pouta

Recommended adjacent checkouts:

```text
/srv/laclaugpt/LaclauGPT-Data-Visualization
/srv/laclaugpt/LaclauGPT-Private
```

Only after confirming permissions, authentication and legal data-location policy:

```bash
cd /srv/laclaugpt/LaclauGPT-Data-Visualization
git pull --ff-only
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e .
export LACLAUGPT_VIS_ANALYSIS_DATA_DIR=/srv/laclaugpt/LaclauGPT-Private/analysis/ep24/dashboard/export
export LACLAUGPT_VIS_DEMO_PASSWORD='<obtain from secured local secret manager>'
streamlit run src/laclaugpt_visualization/ep24_researcher_app.py \
  --server.address 127.0.0.1 --server.port 18512 --server.headless true
```

**Important:** The above private `dashboard/export` path is an existing snapshot
location, **not guaranteed to be the 500-video dataset**. Validate the manifest;
if the dataset ID or counts do not match, do not call this a completed Monday500 demo.
Move the approved Monday500 snapshot into a distinct directory and point the
environment variable there. The application displays missing/incorrect coverage.

Bind only to loopback. An authenticated TLS proxy or approved VPN can expose it
at the requested external `http://86.50.228.141:8502/` address **only once**
CSC network policy, permissions and authentication have been verified.
Do not expose researcher records directly over unauthenticated plain HTTP.
Existing `:8501` and `:8503` remain untouched.

Production should use a separate systemd service with `Restart=on-failure`,
a secured `EnvironmentFile`, and a dedicated user and read-only data directory.
Never put passwords, SSH keys, Allas secrets or Mongo URLs in Git.
Record the deployed Git SHA and snapshot manifest SHA, and verify streamlit
`/_stcore/health` **on the actual server** before marking #242 complete.
No remote deployment is asserted by this document.

## Research UI

- Country/platform/language/date/text filters, FI/PL/PT/combined view, timelines,
  stage coverage and readable source catalogue.
- Evidence inspector presents textual modalities, summaries, concepts,
  Laclaudian discourse, DNA actor–concept statements, evidenced SNA ties,
  typed cross-layer references and RDF availability.
- Research-facing columns are explicitly allowlisted in
  `ep24_researcher.py`. A CSV export goes through the same allowlist.
  Internal IDs, prompts, runtime state and worker metadata are omitted.
- No automatic claim that missing results signify absent political phenomena.
  Aggregates report their units and sources.

## Legacy compatibility audit (initial)

| Legacy feature | Issue #242 implementation | Status |
| --- | --- | --- |
| Wide Streamlit research layout | Wide EP2024 app | Implemented |
| Country/platform/date filters | Sidebar controls | Implemented |
| Publication timeline and platform counts | Plotly figures | Implemented |
| Searchable video records | Streamlit dataframe and selection | Implemented |
| Legacy groovy Plotly visual theme | Not yet copied into new app | Pending |
| Word clouds, violin/radar, animated rankings | No direct replacements yet | Pending |
| Record detail and multimodal summaries | Text-based record inspector | Implemented |
| Laclaudian discourse exploration | Research table and evidence text | Partial |
| DNA graph and evidence | Statement plot and evidence table | Partial |
| SNA visual graph | Evidence table only | Partial |
| Cross-layer graph interactions | Typed edge table/counts | Partial |
| Step 9 RDF | Artifact availability | Partial |
| Live parity screenshot audit of :8501 | Needs browser/server access | Unverified |
| FI/PL/PT actual 500-video exports | Must verify manifest on authorized host | Unverified |
| Running at Pouta :8502 | Needs authorized Pouta access and smoke test | Not deployed |

## Tests

```bash
python -m pytest -q tests/test_issue242_researcher.py
```

Tests cover field allowlists, missing/incorrect cohorts, evidence formatting,
child-column privacy and stage denominators. Full browser checks, real snapshot
verification and server smoke tests remain required for acceptance.
