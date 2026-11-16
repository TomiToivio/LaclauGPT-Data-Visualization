# Approving the 500-video cohort: how the roster was made

The hardened researcher app (#243, #245) refuses to display an export until it can prove the export
*is* the requested cohort. That proof is an approved roster — 1 500 identities, 500 per country —
whose digest the export manifest carries.

Until 2026-11-16 no such roster existed, and the guard demanded something no delivered file
satisfied, so the dashboard could not open at all. This records what the roster is, how this one was
derived, and what it does and does not prove.

## What the roster is

A plain text file, one identity per line:

```text
monday500:finland:<24 hex chars>
monday500:poland:<24 hex chars>
monday500:portugal:<24 hex chars>
```

1 500 lines exactly, 500 per country. `ep24_cohort.read_roster` rejects duplicates, any other prefix,
and any country total other than 500 — the checksum protects against tampering, the counts protect
against a partial snapshot.

The manifest carries the matching block:

```json
"approved_cohort": {
  "schema": "ep24-approved-cohort/1",
  "dataset": "ep24_monday500_20261031",
  "sha256": "<digest of the roster file>",
  "approved_counts": {"finland": 500, "poland": 500, "portugal": 500},
  "roster": "approved_cohort.txt"
}
```

The app compares the roster's digest to the manifest's, then checks every row's `_storage_id`
against the roster. A row outside the roster is a warning and the dashboard stops.

## How this roster was derived

From the delivered checkpoint export
`analysis/ep24/pouta_exports/fiplpt_500_20261115/` (2026-11-15, `producer_revision:
monday500_20261031`):

1. read `_storage_id` from `combined.csv` — 1 500 rows, 1 500 distinct values, no duplicates;
2. group by the country segment — 500 / 500 / 500;
3. sort and write the lines; digest the file.

The export's manifest independently states `input_rows: 500` and `exported_videos: 500` per country
for that producer revision, so the roster and the manifest agree on the cohort *before* the app
checks the digest.

**What this proves:** the displayed rows are exactly the identities this export declared, with no
silent substitution or partial mount.
**What it does not prove:** that those 1 500 videos are the right 1 500 for the study — that is a
sampling decision, recorded in the dataset's own definition, and the roster is the mechanism that
then keeps the dashboard honest about it.

## The correction that made the guard usable

The first version of `ep24_cohort.is_member` also required each row's `dataset` column to equal
`ep24_monday500_20261031`. On the real export that column carries the producer's *pipeline* label,
`ep2024_reprocess`, so the guard rejected all 1 500 correct videos and the dashboard opened to
"Invalid or incomplete Monday500 cohort".

Cohort identity is the roster, the `monday500:<country>:` storage key and the row's country. The
pipeline label is reported to the researcher as provenance (`cohort_notes`), not used as a gate. The
manifest-level check still rejects an export that declares a different cohort.

## Re-making the roster for a new snapshot

```python
# read the snapshot's _storage_id column, verify distinctness and 500/country,
# write approved_cohort.txt, digest it, then put the digest in the export manifest
```

Never derive it from a filtered view, and never let the app fall back to "whatever rows arrived":
the point of the roster is that the cohort was chosen before the dashboard looked at it.
