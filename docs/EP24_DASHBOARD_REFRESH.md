# EP24 dashboard refresh procedure and provenance (#210)

The reprocessed EP24 dashboard (`src/laclaugpt_visualization/ep24_reprocessed_app.py`, served on Laskin at
`:18503`) reads a **copy** of an export from a private directory. Nothing about the dashboard can tell you
whether that copy is the newest completed reprocessing output — so the answer is computed, not eyeballed:

```bash
python scripts/ep24/refresh_ep24_dashboard.py \
    --dashboard "$LACLAUGPT_VIS_PRIVATE/analysis/ep24/dashboard/export" \
    --source    "$LACLAUGPT_VIS_PRIVATE/analysis/ep24/mongo_export" \
    --verbose
```

The check reads two `MANIFEST.json` files and returns one of four verdicts.

| verdict | meaning | action |
|---|---|---|
| `current` | the dashboard is not behind the source | none |
| `stale` | the source has more records, a newer country timestamp, or both | refresh |
| `different_unit` | the two use different record units (`video` vs `ingest`); counts *should* differ | none — the comparison is not meaningful |
| `incomparable` | a manifest is missing a country, reports zero records, or lacks counts | fix the export first |

## Why the two exports disagree on totals, and why that is not rot

Both are `record_unit: video`, but they key identity differently:

- the **streaming** export (`dashboard/export`, 5,306 records) digests `allas_filename + video_id`;
- the **Mongo** export (`mongo_export`, 4,866 records) keys media on `allas_filename` first, falling back
  to `_storage_id`.

Poland collapses furthest (2,112 → 1,781) because its media file spans more rows. Finland agrees exactly
(2,125 = 2,125), which is the useful cross-check: where the two rules can agree, they do.

**Neither number is wrong.** A count must name its identity rule, which is the #195/#205 contract. The
verifier reports this as an identity-rule difference rather than staleness, because a dashboard holding
*more* records than the source is not behind it.

## Procedure

1. **Check.**
   `--verbose` prints per-country records and newest timestamps for both sides.
2. **Produce a newer export, if the source has moved.**
   In `LaclauGPT-Multimodal-Analysis`:
   `python scripts/ep24/export_mongo_results.py --output <new dir> --record-unit video`
   That is read-only against Mongo.
3. **Swap, keeping a backup.**
   `... --swap` moves the current dashboard directory to `export.prev-<UTC stamp>` and copies the source
   in. If the copy fails, the previous directory is restored rather than left empty.
4. **Restart and verify.**
   `... --swap --restart-unit laclaugpt-ep24-demo`, then confirm the app answers and the record counts in
   the UI match the manifest.

`--annotate` counts the per-country CSVs into the dashboard manifest first. The streaming exporter writes a
**totals-only** manifest, which is why a country-level check had nothing to read; annotating adds
`countries: {finland: {records}, …}` and refuses to write when the per-country rows do not sum to the
declared total. Totals-only manifests still work — the verifier falls back to a totals comparison and says
so — but per-country verification needs the block.

`--require-current` exits non-zero when the dashboard is stale, so the check can run from cron or CI.

## Refresh record — 2026-10-28

- **Source database unchanged since the previous export.** Live counts: Finland 3,700 · Poland 3,643 ·
  Portugal 1,946 documents, identical to the 2026-10-27 export's `source_documents`. Nothing has arrived
  to refresh *to*.
- **Dashboard verified current.** 5,306 records; per-country 2,125 + 2,112 + 1,069 = 5,306, reconciling
  with `combined.csv`.
- **Manifest annotated** with the per-country block, so future checks are country-level rather than
  totals-only.
- **Live check:** `http://<laskin>:18503/` returns HTTP 200 after the change.
- A fresh export was regenerated into `mongo_export_20261028/` from the unchanged database to confirm the
  pipeline still runs end to end; its counts match the 2026-10-27 manifest.

## What is deliberately not in this repository

No CSV, JSONL, text bundle or manifest from the private export is committed. The verifier reads paths at
runtime, the tests use synthetic manifests, and the procedure takes a private path as an argument. The
public repository carries code and this document only.

## Limits

- The verifier compares **manifests**, not rows. A source that changed content without changing counts or
  timestamps would pass; the hash list in the export manifest is how to check that (`sha256` per output).
- Country freshness needs `provenance.<country>.newest_timestamp`, which the Mongo exporter writes and the
  streaming exporter does not. Annotating adds counts, not provenance.
- Step-level completeness (steps 0–9) is **not** checked here. That is the stage-coverage audit in
  `LaclauGPT-Multimodal-Analysis` (`scripts/ep24/audit_stage_coverage.py`), and a manifest-level refresh
  check must not be mistaken for it.
