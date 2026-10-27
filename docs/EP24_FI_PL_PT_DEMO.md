# EP24 FI / PL / PT demo — export, dashboard, deployment (issue #195)

Two strictly sequenced deliverables: a **read-only export** of the reprocessed EP24 results, and a
**separate dashboard entrypoint** that presents every available stage without touching AI26 or the
legacy `:8501` / `:8503` services.

Real research data never enters this repository. The export lives in the private
`LaclauGPT-Private` checkout (`analysis/ep24/dashboard/export/`); this repository contains the
exporter, the app, synthetic fixtures and the tests.

## 1. What the export contains

| file | one row per | content |
| --- | --- | --- |
| `combined.csv` | video | every country side by side, with a `country` column and a namespaced `record_key` |
| `<country>.csv` | video | identity, stage statuses, derived counts — the researcher-facing table |
| `text.jsonl.gz`, `<country>_text.jsonl.gz` | video | every stage's human-readable **and** machine-readable output, keyed by step |
| `entities.csv` | entity/theme mention | `kind` distinguishes Step 5 model output from legacy entity columns |
| `discourse_claims.csv` | Laclau/Palonen coding section | Step 6 hypotheses, traceable to the record |
| `dna_statements.csv` | actor–concept statement | Step 7, with the evidence quote when the producer supplies one |
| `sna_nodes.csv`, `sna_edges.csv` | node / edge | Step 8 empirical graph; an edge exists only where the producer emitted one |
| `rdf_resources.csv` | record with Step 9 metadata | Step 9 status/resources when the producer writes them into the frame |
| `MANIFEST.json` | — | source hashes, row counts, stage coverage, kept/dropped columns **with reasons** |
| `QA_REPORT.md`, `DATA_DICTIONARY.md` | — | what is present, what is missing, what failed to parse |

`record_key` is `country/<video_id>#<digest>`: the digest covers the media key, recording, segment
and platform, because `video_id` alone **collides** in the EP24 corpus (up to nine rows share one id).
Identical tuples are the only thing counted as a duplicate, so distinct videos are never merged.

## 2. Coverage in this delivery (measured, not assumed)

| country | source | profile | records | steps available |
| --- | --- | --- | ---: | --- |
| Finland | Roihu cumulative reprocessed frame | `reprocessed` | 2125 | 0–8; Step 9 is file-based, so unavailable in-frame |
| Poland | legacy 75-column dashboard export | `legacy` | 2112 | none of the reprocessed steps; legacy transcript/OCR/summary/entities only |
| Portugal | legacy 75-column dashboard export (filtered from the shared 8501 file) | `legacy` | 1069 | as Poland |

Finland's measured stage coverage (denominator 2125): ingest 2124, preprocess 2125, keyframe 2124,
video 1276, summary 1050, postprocess 1037, discourse 707, DNA 660, SNA 624, RDF 0 (file-based).
Normalized children: 12 398 entity/theme mentions, 7 890 discourse claims, 1 508 DNA statements,
1 838 SNA nodes, 1 393 evidence-carrying edges. Export size ≈ 65 MB.

The honest gap: **the reprocessed Roihu cumulative frames for Poland and Portugal are not present in
any reachable location** (checked: private repo `analysis/ep24/source/`, OneDrive, `Laskin`
`~/ep24-pl-pt-se-wt`, Allas `HEPP24`). Their `--profile legacy` export therefore reports every
reprocessed stage as *unavailable* rather than as zero records, and the dashboard shows exactly that.
When the PL/PT cumulative frames appear, adding them is one `--source` flag — no code change.

## 3. Refresh the export

```bash
python scripts/ep24/export_visualization_data.py \
  --source finland=/data/ep24_finland_reprocessed_complete.csv \
  --source poland=/data/ep24_poland_dashboard.csv:legacy \
  --source portugal=/data/ep24_8501_dashboard.csv:legacy --filter-country portugal=Portugal \
  --output ~/work/LaclauGPT-Private/analysis/ep24/dashboard/export
```

The exporter fails on an **unclassified producer column** (`--fail-on-unaccounted`, default), so a
producer contract change is a red build, not a silently empty chart. It refuses to write into the
source directory and never opens anything but local files.

## 4. Run and deploy the dashboard

```bash
export LACLAUGPT_VIS_ANALYSIS_DATA_DIR=~/ep24_demo/data
streamlit run src/laclaugpt_visualization/ep24_reprocessed_app.py \
  --server.port 8502 --server.address 0.0.0.0 --server.headless true
```

Deployed for this issue on **SpectacleScraper (86.50.228.141), port 8502** — a distinct endpoint from
the legacy `:8501` / `:8503` on the Streamlit host, which are untouched. The app directory is
`~/ep24_demo/` (code + `data/`, no credentials in any file).

## 5. Legacy vs new: what changed

| legacy `:8501` / `:8503` | this demo |
| --- | --- |
| one row per video with summary fields | same one-row-per-video table, plus every stage's machine output |
| no Step 6/7/8/9 | dedicated discourse (6), DNA (7), SNA (8) and RDF (9) views |
| no coverage accounting | `MANIFEST.json` + stage coverage with denominators; missing stages shown as unavailable |
| no evidence drilldown | tables select a row and the inspector follows; every graph edge carries its source |
| unlabelled provenance | model output, researcher notes and derived counts are separate, labelled columns |
| no export contract | field allowlist with per-column drop reasons, and an unaccounted-column failure |

## 6. Limits stated plainly

- The endpoint is a plain HTTP Streamlit port, like the legacy dashboards: there is no authentication
  layer. If the corpus is access-restricted, use an SSH tunnel
  (`ssh -L 8502:localhost:8502 SpectacleScraper`) instead of the public URL.
- Polish and Portuguese rows are legacy-schema only (see §2).
- Step 9 is a filesystem projection upstream, so it is reported as unavailable unless
  `graph.ttl`/`graph.nt` are exported into the data root.
- Frequency and centrality are never presented as interpretations of hegemony.
