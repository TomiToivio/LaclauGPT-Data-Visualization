# EP24 FI/PL/PT reprocessed demo (issue #195)

## Isolation and privacy

The public Visualization repository contains **code and synthetic tests only**.
Keep raw cumulative data, cleaned exports, optional media, private research notes,
institutional credentials and any deployment secrets **outside the public checkout**.
The private LaclauGPT-Private repository can store private configuration and
restricted documentation; large or sensitive datasets should remain on approved
CSC private storage, mounted into the private data root. A private GitHub repo is
not automatically an approved store for sensitive research records.

## Export on an authorized host

Install the repository, then run from the repository root with your authorized
Roihu cumulative checkpoints. The exporter only reads its inputs.

```bash
python -m pip install -e .
python scripts/ep24/export_demo.py \
  --finland /private/input/finland.csv \
  --poland /private/input/poland.csv \
  --portugal /private/input/portugal.csv \
  --output /private/LaclauGPT-Private/analysis/ep24/demo-export
```

`export_demo.py` is a thin adapter over `export_visualization_data.py`, which streams the frame
(a 1.1 GB cumulative CSV is normal, so the file is never loaded whole) and chooses, for a video that
appears several times, the row that carries the **most** stage output rather than the first one.

Inspect `MANIFEST.json` for source hashes, row counts per country (read / exported / duplicates /
unusable ids) and per-stage coverage with denominators; `QA_REPORT.md` says what is missing and what
failed to parse. Outputs are `combined.csv`, three country CSVs, a gzipped text bundle with each
stage's human- and machine-readable output (`text.jsonl.gz`, `<country>_text.jsonl.gz`), the child
tables `entities.csv`, `discourse_claims.csv`, `dna_statements.csv`, `sna_nodes.csv`,
`sna_edges.csv`, `rdf_resources.csv`, plus `MANIFEST.json`, `QA_REPORT.md` and
`DATA_DICTIONARY.md`. Every column is either kept, derived or dropped **with a reason**, and an
unclassified producer column fails the build rather than disappearing.

**Country casing and shared files.** Real frames say `Poland`, not `poland`, and the Portuguese
rows live inside a shared export that also holds other countries; an exact lowercase match aborts the
export. Use `--filter-country portugal=Portugal` for a shared file, and `:legacy` on a source whose
frame predates the Roihu steps — every reprocessed stage is then reported as *unavailable*, never as
zero records. Do not interpret a stage's present output as human-validated research.

Step 9 RDF files must be copied/mounted separately with permission; the
exporter deliberately does not claim a per-record RDF completion state from
global file presence.

## Pouta deployment

A Streamlit demo entrypoint already exists at
`src/laclaugpt_visualization/ep24_reprocessed_app.py`, separate from AI26.
To launch this dedicated version:

```bash
export LACLAUGPT_VIS_ANALYSIS_DATA_DIR=/private/LaclauGPT-Private/analysis/ep24/demo-export
bash scripts/ep24/run_reprocessed_demo.sh
```

Deploy as a **separate** systemd user/service using
`deploy/laclaugpt-ep24-demo-pouta.service.example`; the loopback listener
on port 18512 should be published only through an approved authenticated TLS
reverse proxy or private VPN. Do not replace services on 8501/8503 or publicly
expose private source videos, records or exports. Confirm CSC Pouta network
policy, storage permissions, institutional data processing restrictions,
authentication and auditing before sharing the demo.

### Outstanding deployment gates

1. Authorized access to the **actual FI/PL/PT cumulative processed checkpoints**
   and evidence that the new steps have completed.
2. Private Pouta or SpectacleScraper shell/deployment access, secure TLS proxy,
   and permitted external exposure policy.
3. Verification of live app visuals, backend resource limits, country-specific
   fields, completion report and usability on **real** datasets.

Do not claim the application is hosted or the research demo is complete until
the deployment URL is checked end to end against actual private data.
