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

Two properties of the real frames are handled explicitly, because both used to abort the export:

* **a repeated identity** — a cumulative frame carries one video through several runs, each with
  more stage output. The most complete row wins, the rest are counted in
  `manifest.json → duplicate_rows_merged`; the merge is never silent.
* **a shared source** — the Portuguese rows live inside the shared legacy `:8501` export that also
  holds Finland, Poland, Sweden, …. Pass `--filter-country portugal=Portugal` to select that country
  out of the file. Without a selector, a country mismatch still fails: two countries are never
  silently merged.

Inspect `manifest.json` for excluded bad IDs, row counts per country, merged duplicate rows,
and per-stage availability. Outputs are `combined.csv`, three country CSVs,
`records.jsonl`, child relation CSVs, and the manifest. The allowlist omits
intermediate prompts, caches and scratch state while retaining final analyses.
Structured child records remain JSON in `item_json` with stable `record_id`.
Do not interpret a stage's present output as human-validated research.

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
