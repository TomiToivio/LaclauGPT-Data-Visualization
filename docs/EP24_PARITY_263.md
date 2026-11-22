# EP24 dashboard parity (#263) — what `:8502` can and cannot do

Scope: the **reading half** of the legacy `:8501` workbench, on the reprocessed FI/PL/PT
export. The curation **write path** is deliberately not built: #263 §4 asks the owner to
choose between a MongoDB review collection (a), append-only review events in
`LaclauGPT-Private` (b), or reading-only now (c). This implements (c), the issue's own
recommendation, and leaves the decision open rather than inventing a second write path
nobody audited.

Mechanism: `src/laclaugpt_visualization/ep24_researcher_parity.py`, rendered by the
`Researcher reader · parity` and `Aggregates · parity` views. The parity claim is
machine-checked by `tests/test_ep24_parity_263.py` (acceptance criterion 5), so the table
below cannot rot silently.

## Per-record tabs

| legacy tab | new source columns | state |
| --- | --- | --- |
| Metadata | `country`, `source_type`, `account_type`, `political_preference`, `video_duration_seconds` | mapped |
| Whisper transcript | `asr_transcript` | mapped |
| Whisper translation | `asr_translation` | mapped |
| OCR (frame 1) | `ocr_1` | mapped |
| Multimodal (frame 1) | `frame_analysis_1`, `vllm_video_analysis` | mapped |
| Summary | `summary_analysis`, `summary_summary_md` | mapped |
| Populism | `formula_of_populism_analysis`, `+_us`, `+_frontier` | mapped (richer than legacy) |
| Themes | `postprocess_themes` (child table `children/themes.csv` upstream) | mapped |
| Persons | `postprocess_entities` (child table `children/entities.csv` upstream) | mapped |
| Report problems / Researcher notes | `researcher_note` | mapped, **read-only** — a note typed here is not persisted |

## Aggregate tabs

| legacy tab | new source | state |
| --- | --- | --- |
| Frequency | `country`, `source_type` | mapped |
| Entities | `postprocess_entities` | mapped |
| Sentiments | `positive`, `neutral`, `negative` | mapped |
| Languages | `source_language`, `language` | mapped |
| Statistics | `political_preference`, `source_type` | mapped |
| Themes | `postprocess_themes` | mapped |
| Persons | `postprocess_entities` | mapped |
| **Topics** | — | **absent**: no `lda_topic` column or child table in the reprocessed export |
| **ManifestoBERTa** | — | **absent**: no `manifestoberta_predicted_class`; the stage is not in the pipeline |

Absent tabs are listed in the UI with their reason and are never rendered as an empty
chart, because an empty chart reads as "the phenomenon is missing" rather than "the column
is missing".

## Rules the charts now follow

- **Denominator.** Every count states the rows it was drawn from, including blanks — not
  the corpus size. Two exports legitimately disagree on totals.
- **Identity.** Every count states its identity rule (`video_id` when present, otherwise
  "one record per exported row"), so duplicate or unidentified records are visible instead
  of averaged away.
- **`platform` is derived**, from `source_type` + `account_type`. The legacy column does
  not exist, and the derivation changes what the chart means, so it is stated next to it.
- **The date filter names its column** (`created_at`, `published_at`, `recorded_at`,
  `timestamp`, `source_recording` — first present wins).

## Not done here

1. **Write path** — see §4 above; owner decision required.
2. **Manifest verification of the committed tree** (criterion 4): `manifest.json` in
   `LaclauGPT-Private/analysis/ep24/pouta_exports/fiplpt_500_20261115/` declares 28 files in
   a *flat* layout while the tree is per-country, so 26 of 28 declared files are missing.
   That is a defect in the private data repository, not in this code, and regenerating it
   needs the producer's file list — filed as a follow-up rather than guessed at here.
3. **One layout** (criterion 4, second half): the host serves a third, flat assembly of the
   same data. Choosing the canonical layout is a data-repository decision with the same
   blocker as (2).
