# Refresh EP24 FI/PL/PT dashboard from Multimodal-Analysis (issue #210)

The source of truth is the **shared MongoDB reprocessed video dataset**, exported
read-only by `LaclauGPT-Multimodal-Analysis/ep24_mongo_dashboard_export.py`.
Do not use repository fixtures, old demo CSVs, or the legacy exporter as a substitute.

## Authorized runtime procedure

On an authorized machine with the analysis repository checked out and the shared
MongoDB URI in its *private* environment:

```bash
# Run in LaclauGPT-Multimodal-Analysis (requires configured private Mongo access):
python ep24_mongo_dashboard_export.py --countries fi pl pt \
  --output /approved/private/ep24/exports/candidate

# Run in LaclauGPT-Data-Visualization:
python scripts/ep24/validate_mongo_refresh.py /approved/private/ep24/exports/candidate

# Only after validation, switch the privately configured data-root to the
# candidate directory, then restart the separate EP24 Streamlit service.
export LACLAUGPT_VIS_ANALYSIS_DATA_DIR=/approved/private/ep24/exports/candidate
bash scripts/ep24/run_reprocessed_demo.sh
```

The validator checks canonical video identities, all three country CSVs,
combined row counts, exported manifest counts, step coverage metadata and
provenance timestamps. It does **not** assert that all stages finished.
Read `MANIFEST.json` for `stage_coverage`, `failed_or_other` and
`stage_unavailable`. Partial source output remains partial on screen.

Record the manifest `generated_at`, `contract`, exported counts and analysis
commit SHA privately with the deployment change. For repeatable refreshes,
generate into a new directory; do not overwrite the directory currently
served. Switch the service to a verified candidate and keep the previous
private snapshot for rollback.

**Not performed by this PR:** live Mongo export, changes to Pouta service
configuration, restarting a live dashboard or validating actual research
coverage. These require authorized runtime access. The GitHub repository
contains only export validation code, synthetic tests and this runbook.
