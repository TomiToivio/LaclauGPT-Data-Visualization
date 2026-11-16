# Legacy `:8501` parity on the reprocessed export (#263)

The legacy `ep2024_postprocess` dashboard (`dashboard.py`, `:8501`) is a **curation workbench**: a
researcher opens one video, reads nine tabs, and records a decision. Issue #263 asks for that behaviour
at `:8502` over the reprocessed FI/PL/PT demo (500 + 500 + 500 videos), keeping the evidence discipline
of the reprocessed explorer.

This page is the parity record the dashboard itself renders: for every legacy tab, either a mapped
source in the new export, or the reason it cannot exist. The mapping is executable
(`src/laclaugpt_visualization/ep24_workbench.py`, `legacy_parity()`), and
`tests/test_issue263_ep24_workbench.py` reads it.

## Increment status

| increment (#263 §7) | state |
| --- | --- |
| 1. Private export manifest/layout | done in `LaclauGPT-Private` (#77): `files` describes the committed per-country tree, 25 files with SHA-256 and row counts |
| 2. Per-record reader (read-only) | **this change** — view *Video workbench · legacy parity* at `:8502` |
| 3. Aggregate tabs | specified below, not built yet |
| 4. Write path | not implemented — §4 decision, below |

## Per-record tabs (§1.2 of the issue)

| legacy tab | source in the reprocessed export | state |
| --- | --- | --- |
| Metadata | `country`, `source_type` + `account_type`, `political_preference`, `author_username`, `source_url`, `created_at` / `source_recording`, `video_duration_seconds`, `asr_language`, `video_id` | mapped |
| Whisper | `asr_transcript`, `asr_translation` (`whisper_transcript` / `whisper_translation` on older exports) | mapped |
| OCR | `ocr_1` | mapped |
| Multimodal | `frame_analysis_1`, `vllm_video_analysis`, `vllm_video_markdown_analysis` | mapped |
| Summary | `summary_analysis`, `summary_summary_md`, `postprocess_summary_md` | mapped |
| Populism | `formula_of_populism_analysis` / `_us` / `_frontier`, plus the richer `laclau_summary_md` | mapped, **richer than legacy** (full Laclaudian coding is step 6) |
| Themes | child table `children/themes.csv` keyed on `source_key` (`postprocess_themes` on the row dialect) | mapped |
| Persons | child table `children/entities.csv` keyed on `source_key` (`postprocess_entities` on the row dialect) | mapped |
| Report Problems / Researcher Notes | `researcher_note` is read; **no write** | reading only |

Two behaviours that are deliberate, not omissions:

- **Unavailable is not empty.** A tab whose fields this export does not carry names the fields it looked
  for. "No OCR for this record" and "the video has no visible text" are different findings, and the
  legacy dashboard could not tell them apart.
- **Derived fields say they are derived.** The legacy charts group by `platform`, which is not an
  exported column: `platform = source_type + account_type`. The Metadata tab states the derivation
  instead of presenting it as an observation.

## Aggregate tabs (§1.3 of the issue)

Specified here so the parity claim answers for all eighteen legacy tabs; the panels land in the next
increment.

| legacy tab | source | state |
| --- | --- | --- |
| Frequency | `country`, `political_preference`, `source_type`, `video_duration_seconds` | mapped, not built yet |
| Entities | child `entities.csv` | mapped, not built yet |
| Topics (LDA) | **none** | **no source** |
| Sentiments | `positive` / `neutral` / `negative` + child `sentiment_targets.csv` | mapped, not built yet |
| Languages | `asr_language`, `source_language`, `language` | mapped, not built yet |
| ManifestoBERTa | **none** | **no source** |
| Statistics (per-country preference/platform) | `country`, `political_preference`, `source_type` | mapped, not built yet |
| Themes over time | child `themes.csv` + a dated field | mapped, not built yet |
| Persons over time | child `entities.csv` + a dated field | mapped, not built yet |

### Tabs with no source at all

- **Topics (LDA)** — the reprocessed pipeline produces no `lda_topic`; topics were a legacy postprocess
  artefact.
- **ManifestoBERTa** — no `manifestoberta_predicted_class`; the pipeline does not run ManifestoBERTa.

These are **absent and listed**, never rendered as an empty chart. An empty chart reads as "the corpus
contains none", which is a claim about the corpus rather than about the pipeline.

## Dates: name the field, not "the date"

The legacy date filter used `recording_date`. The new export carries `created_at`, `timestamp` and
`source_recording`, and they are not the same day. Any date filter or timeline must say which field it
filters — the existing app prefers `created_at`, then `published_at`, then `source_recording`, in that
order, and should say so on screen when the choice is ambiguous.

## The write path (#263 §4) — undecided, therefore not built

Legacy wrote `video_checked`, `delete_video`, `dubious_video`, `rerun_llm`, `rerun_ocr`, `rerun_whisper`,
`cut_video` + `cut_at` + `cut_keep`, `split_video` + `split_at`, `new_persons`, `new_themes` and
`researcher_note` into MongoDB. The `:8502` app is read-only by contract.

The three options — (a) a MongoDB review collection, (b) append-only review events in the private
repository, (c) reading only for now with curation staying in legacy — are an owner decision because
they decide what "the data" is for the next paper. **This increment is (c): the reading half, no write
path.** The notes tab says so on screen rather than showing a form whose submit has nowhere to go.

## Counts

Every aggregate and every coverage figure names its denominator and its record unit. Two exports
legitimately disagree on totals when they key identity differently (`video` vs `ingest`); a count without
its identity rule is not a claim. See `EP24_DASHBOARD_REFRESH.md` for the identity-rule comparison.
