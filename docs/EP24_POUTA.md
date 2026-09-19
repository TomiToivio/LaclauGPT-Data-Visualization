# EP24 improved visualization on CSC Pouta

This deployment consumes the private Finland/Poland reprocessing handoff produced by
[LaclauGPT-Data-Analysis #245](https://github.com/TomiToivio/LaclauGPT-Data-Analysis/issues/245).
It deliberately uses local files only. MongoDB, Redis and S3 are not required.

## Expected private handoff

Point `LACLAUGPT_VIS_ANALYSIS_DATA_DIR` at either the EP24 root or its `data/` directory.
The loader searches for:

```text
<private-ep24-root>/
  data/
    combined.csv
    finland.csv
    poland.csv
    ep24.sqlite3
    legacy_comparison.csv
    failures.csv
  outputs/
  provenance/
  qa/
```

`combined.csv` is preferred for the dashboard because it preserves Finland/Poland identity
in one inspectable frame. If CSV is absent, `ep24.sqlite3` is accepted when it contains
`combined`, `records` or `annotations`.

The CSV/SQLite files remain the source of truth. Visualization does not write analysis results.

## VM setup

Create a normal Python virtual environment and install the repository:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

No `remote` extra is needed for the EP24 Pouta mode.

## Run

```bash
export LACLAUGPT_VIS_ANALYSIS_DATA_DIR=/private/path/to/analysis/ep24
bash scripts/ep24/run_ep24_dashboard.sh
```

Defaults:

- project ID: `ep24`
- local CSV/SQLite/filesystem storage
- in-memory cache
- no Redis messaging
- no S3
- loopback bind
- Streamlit port `18502`

Use SSH forwarding from the researcher workstation:

```bash
ssh -N -L 18502:127.0.0.1:18502 POUTA_HOST
```

Then open `http://127.0.0.1:18502` locally.

Do not expose row-level research data directly to the public Internet. If a private deployment
needs non-loopback binding, put Streamlit behind an authenticated TLS reverse proxy and set
`LACLAUGPT_VIS_ALLOW_NONLOOPBACK=1` explicitly.

## What the EP24 page shows

When `LACLAUGPT_VIS_PROJECT_ID=ep24`, the normal workbench gains an **EP24 Improved** page
with:

- Finland/Poland corpus coverage;
- analyzed/failure/codebook-reference counts;
- country-preserving signifier, nodal-point, entity, topic, frontier and affect tables;
- Finland/Poland comparison charts;
- exported relation edges;
- `legacy_comparison.csv` summary and row inspection;
- QA metrics and `failures.csv` inspection.

The existing Researcher Review page remains the row/document inspector for source material,
legacy aliases, intermediate outputs, structured analysis, evidence, uncertainty, provenance
and human review state.

Counts and network relations remain descriptive. They do not establish nodal, floating or
empty-signifier status, antagonism, equivalence or hegemony without the underlying analysis
and human interpretation.

## Refresh after a Roihu run

The dashboard reads the handoff from disk on Streamlit rerun. After copying or synchronizing
a new #245 result bundle to the configured private directory, refresh the browser or restart
the service. There is no application rebuild and no database migration.

A safe operational pattern is:

```bash
# synchronize private #245 outputs using your approved CSC transfer method
sudo systemctl restart laclaugpt-visualization-ep24
```

Do not commit the synchronized files to this public repository.

## systemd

Copy and edit the public example:

```bash
sudo cp deploy/laclaugpt-visualization-pouta-ep24.service.example \
  /etc/systemd/system/laclaugpt-visualization-ep24.service
sudo systemctl daemon-reload
sudo systemctl enable --now laclaugpt-visualization-ep24
```

Replace all placeholder paths/users in the copied unit. Keep environment files and private
paths outside Git.

## Troubleshooting

Check the non-secret runtime profile:

```bash
LACLAUGPT_VIS_PROJECT_ID=ep24 \
LACLAUGPT_VIS_ANALYSIS_DATA_DIR=/private/path/to/analysis/ep24 \
laclaugpt-visualize profile
```

If the EP24 page reports `storage: empty`, verify that `combined.csv` or a supported SQLite
table exists below the configured analysis root. Missing companion files do not stop the
dashboard; their panels state that the export is unavailable.
