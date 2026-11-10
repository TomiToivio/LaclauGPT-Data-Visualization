# FI/PL/PT live pipeline explorer — steps 1–7

A researcher-facing view over the three live `*_live_steps_1_7.csv` exports (Finland, Poland,
Portugal). Served at <http://195.148.31.227:8503/>.

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

**One producer defect, repaired and recorded:** the Portugal CSV cannot be parsed as a single stream
(the producer's quoting merges records — a whole-file parse yields 3 rows for 500 videos). The builder
splits the file on its own record boundary (`^monday500:`) and asserts every block parses to the full
field width. No Portugal row was dropped, and the manifest says so.

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
