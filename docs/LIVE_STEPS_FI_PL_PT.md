# FI/PL/PT live pipeline explorer — steps 1–7

A researcher-facing view over the three live `*_live_steps_1_7.csv` exports (Finland, Poland,
Portugal). Served on **Laskin** at <http://100.115.95.109:8503/> (Tailscale address of `laskin01`).

## What the export contains

| | Finland | Poland | Portugal | total |
|---|---|---|---|---|
| videos | 500 | 500 | 500 | **1 500** |
| recording months | 2024-05 … 2024-06 | 2024-05 … 2024-06 | 2024-05 … 2024-06 | |
| all 7 steps complete | 500 | 420 | 471 | **1 391** |
| SNA edges present | 472 | 24 | 224 | **720** |

Every record carries ASR, OCR, frame VLM, video VLM, a multimodal summary, a Laclau discourse
reading and (mostly) a DNA statement list. Video VLM, summary, postprocess and the discourse stages
are complete for all 1 500; **step 8 (social network) is partial** — 720 videos have it — and that is
shown in the UI as coverage, never as "no relations found".

## Cleaning, and what it removed

Source: three CSVs, 1.85 GB, 182–190 columns each.

- **0 duplicate rows** on `(country, video_id)` — the export has one row per video. The rule is still
  implemented (most-complete row wins, ties broken by content volume) because the next export will
  not necessarily be clean.
- **52 intermediate columns dropped**, each with its reason in the manifest: retrieval/codebook/memory
  context dumps (≈470 MB of prompt input), raw model responses, prompts and their hashes, local and
  remote paths, content hashes, `_pipeline`/`_provenance` orchestrator blobs, EP24 ingest and
  normalisation bookkeeping. They are prompt plumbing, not findings.
- **Kept**: identity and metadata, every per-stage status/model/runtime/timestamp, every human-readable
  output (transcript, OCR text, frame and video analyses, summary, Laclau reading, DNA statements and
  analysis, SNA report), entities, themes and sentiment targets, and the three step counters.
- Artifacts: index CSVs 6.5 MB, text bundles 14 MB gzipped, DNA statement tables 1.4 MB — **1.8 GB →
  28 MB**, and every long value is verbatim.

**Parsing note (measured, and the reason the builder uses the stdlib reader):** the Portugal export is
a valid CSV — Python's `csv` module reads all three files whole (500 records × 182/185/190 fields).
DuckDB's `read_csv` mis-detects quoting on it: strict mode fails with `CSV Error on Line: 1`,
`ignore_errors=true` silently yields **3 rows for 500 videos**, and `strict_mode=false` gives one row
per physical line (399 766). The builder therefore reads with `csv`, asserts every row parses to the
header width, and never runs with error-dropping on. If you profile these files with DuckDB, do not
trust `ignore_errors` — it will quietly delete the corpus.

## Artifact contract

```
analysis/live_steps_1_7/          (private: TomiToivio/LaclauGPT-Private)
  finland.csv  poland.csv  portugal.csv   index: one row per video, short scalars
  *_text.jsonl.gz                          long cells + DNA statements / SNA edges keyed by record_id
  children/<country>_dna_statements.csv    normalized statements, joined on _storage_id
  combined.csv                             the three indexes stacked
  MANIFEST.json                            per-column keep/drop + reason, stage coverage, audit
```

## Rebuild

```bash
cd LaclauGPT-Data-Visualization
python tools/build_live_steps_artifacts.py \
    --source-dir "<directory with the three CSVs>" \
    --out ../LaclauGPT-Private/analysis/live_steps_1_7
```

The builder refuses to finish while any source column is unclassified, so a pipeline change that adds
a field fails the build instead of silently vanishing from the dashboard.

## Run the app

```bash
LACLAUGPT_VIS_LIVE_STEPS_DATA=../LaclauGPT-Private/analysis/live_steps_1_7 \
  streamlit run src/laclaugpt_visualization/live_steps_app.py --server.port 8503
```

Tests: `pytest tests/test_live_steps_artifacts.py tests/test_live_steps_app.py` (17 tests; the app
tests execute the real script through `streamlit.testing.v1.AppTest`).

## What the views are for

- **Overview / Aggregates** — corpus shape: country, platform, political preference, recording month,
  duration, steps completed; top entities, themes, sentiment targets, ASR language.
- **Steps & coverage** — per-stage coverage against each country's exported denominator, and the
  producer's own status vocabulary, so "ran" is visibly distinct from "produced something usable".
- **Record browser** — one video: metadata, then one expander per step with its verbatim output from
  the text bundle (transcript, OCR, frame analysis, video analysis, summary, Laclau structured output,
  DNA statements table, SNA edges).
- **Discourse · DNA** — statement counts, top actors and organizations, discourse layers, and the
  statements themselves with their evidence quotes. A statement is an interpretation of a text, never
  a fact about a person; a graph position is a lead, never proof.
- **Network · SNA** — edges by type, confidence distribution, most connected nodes, and every edge
  with the quote it was drawn from.
- **Data quality / Methods** — the audit above, rendered from the manifest.

## Honest gaps

- Recording dates are derived from the media id (`…-YYYYMMDD-…`), not a producer field; the UI says so.
- `political_preference` is the producer's coding (Centre right / Far right / Red-green); the dashboard
  never treats it as a finding.
- No authentication layer; the export is private and the port is public, so it must stay a read-only
  research demo until access control is added.
- Step 8 is partial (720/1 500). Nothing in the UI infers missing SNA as absent relations.

## Deployment on the research server (`195.148.31.227:8503`, verified)

| Item | Value |
| --- | --- |
| URL | <http://195.148.31.227:8503/> |
| Code | a checkout of this repository on the server, `origin/main` |
| Data | `LACLAUGPT_VIS_LIVE_STEPS_DATA` → the private artifact directory synced from `LaclauGPT-Private` |
| Launcher | `analysis/live_steps_1_7/deploy/run.sh {start,status,stop,health,rollback}` in the private repository |
| Process | `setsid --fork python -m streamlit run src/laclaugpt_visualization/live_steps_app.py --server.port 8503` |
| Health | `curl -s http://195.148.31.227:8503/_stcore/health` → `ok` |
| Log | `$HOME/.local/state/laclauGPT-live-steps/streamlit.log` |

The private repository's `deploy/README.md` carries the paths, the refresh recipe, the restart policy
and the rollback. The port previously served the EP24 reprocessed export from another directory; that
directory is untouched and restarting its old command is the last-resort rollback.

The export carries author usernames, video identifiers and transcripts, and the app has no
authentication unless `LACLAUGPT_VIS_DEMO_PASSWORD` is set. Current posture: a read-only research demo on
a known host, publicly reachable, with the gate available and documented. That is a decision to take
deliberately — the gate must be set before this is treated as anything other than a demo.

## Deployment on Laskin (:8503, reported by another session, not verified from here)

The app is public code; the artifacts are private data. The server runs the app from a clean checkout of this
repository and reads the artifacts through an environment variable, so nothing private is ever copied here.

**Live URL:** <http://100.115.95.109:8503/> — the server's Tailscale address. The process binds to that
interface only, matching the legacy dashboard on :8501: the data includes transcripts, video ids and author
handles and the demo has no authentication of its own, so the network boundary *is* the access control until
an authenticated deployment is agreed.

| Item | Value |
| --- | --- |
| Service | `laclaugpt-live-steps.service` (systemd user unit, `Restart=on-failure`) |
| Working directory | a clean checkout of this repository on the server, at `origin/main` |
| Launcher | `scripts/serve_live_steps.sh 8503 100.115.95.109` |
| Data root | `LACLAUGPT_VIS_LIVE_STEPS_DATA` → the private artifact directory (`analysis/live_steps_1_7` in `LaclauGPT-Private`; its `deploy/README.md` is the source of truth for paths) |
| Health | `curl -s http://100.115.95.109:8503/_stcore/health` → `ok` |
| Logs | `journalctl --user -u laclaugpt-live-steps.service -n 50` |

### Update

```bash
git pull --ff-only                                        # in the server's checkout of this repository
git -C "$PRIVATE_CHECKOUT" pull --ff-only                 # refreshed artifacts, if any
systemctl --user restart laclaugpt-live-steps.service
curl -s http://100.115.95.109:8503/_stcore/health
```

### Rollback

```bash
systemctl --user disable --now laclaugpt-live-steps.service   # :8503 down, :8501 untouched
git checkout <previous-sha>
systemctl --user enable --now laclaugpt-live-steps.service
```

The legacy dashboard on :8501 is a **different unit** (`laclaugpt-visualization-ai26.service`); nothing in this
deployment restarts it.

## Compatibility with the legacy :8501 dashboard

The legacy app (`ep2024_postprocess/dashboard/dashboard.py`, served on :8501, 3 500+ lines) is the
researcher's familiar surface. This app borrows its conventions where the data supports them and
departs where it cannot. :8501 itself is untouched.

| Legacy :8501 | Here | Why |
| --- | --- | --- |
| sidebar filters (country, platform, political preference, search) | same filters, same names | muscle memory; the filters drive every tab |
| KPI cards at the top | same (videos, countries, all-7-steps, with-SNA) | numbers a researcher quotes |
| per-video browser with a tab per model | per-video browser with a **step selector 1–7** (+SNA) | the export is organised by pipeline step, not by model name |
| Frequency / Entities / Topics / Sentiments / Languages / Statistics tabs | Overview, Aggregates, Problems | same questions, fewer, cross-filtered |
| "Report Problems" | Problems | every record with a non-ok status, with the producer's own reason |
| multimodal evidence side by side | one stage at a time, verbatim, with the stage's status beside it | the export has one value per stage, not per model variant |
| — | Search over transcripts/OCR/analyses | the legacy dashboard could not full-text search the corpus |
| — | DNA statements + actor–concept graph | steps 6–7 did not exist in EP24 |
| — | Exports of the filtered tables | requested by #62 |
| per-video URL parameters | Streamlit selection state, no deep links | gap: a link cannot yet address one record |

**Gaps, stated plainly:** no deep-linkable record URLs; no side-by-side model comparison (the export
carries one value per stage); the legacy dashboard's ManifestoBERTa and topic-model views have no
counterpart because those steps are not in this export.

