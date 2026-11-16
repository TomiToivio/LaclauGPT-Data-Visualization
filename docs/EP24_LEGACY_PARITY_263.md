# Legacy parity: what the `:8502` workbench can and cannot reproduce (#263)

The legacy EP24 dashboard at `:8501` is a curation workbench. `.github` of this work: reproduce its *reading*
surface on the reprocessed FI/PL/PT export, and declare — in code and in this file — every part of it that the
reprocessed data cannot support.

Two rules, both enforced by `tests/test_ep24_legacy_parity_263.py`:

1. **A tab with no source is declared, never rendered empty.** An empty chart teaches a researcher nothing and
   tells the next agent that the pipeline is broken.
2. **Every count names its denominator.** The filtered frame is the denominator for every figure in the
   workbench, and the caption says so. This is the repository's existing count rule (#205) applied to the UI.

## Per-record tabs (`dashboard.py:637–760`)

| legacy tab | reprocessed source | status |
| --- | --- | --- |
| Metadata | `video_id`, `country`, `source_type`, `account_type`, `political_preference`, `timestamp`, `video_duration_seconds` | available |
| Whisper | `asr_transcript`, `asr_translation` | available |
| OCR | `ocr_1` | available |
| Multimodal | `frame_analysis_1`, `vllm_video_analysis` | available |
| Summary | `summary_analysis`, `summary_summary_md` | available |
| Populism | `formula_of_populism_analysis`, `+_us`, `+_frontier`, `laclau_abstention_reason` | available, and richer than legacy |
| Themes | child table `children/themes.csv` (`postprocess_themes`) | available as a child table, not a row column |
| Persons | child table `children/entities.csv` (`postprocess_entities`) | available as a child table, not a row column |
| Report Problems / Researcher Notes | `researcher_note` | **read-only**: existing notes are displayed, new ones are not written (see the decision below) |

## Aggregate tabs (`dashboard.py:768–1132`)

| legacy tab | reprocessed source | status |
| --- | --- | --- |
| Frequency | `timestamp`, `political_preference`, `video_duration_seconds` | counts and total duration, per grouping column |
| Entities | child `postprocess_entities` | top labels across the filtered records |
| Topics | — | **no source**: LDA topics were legacy-produced; reproducing the tab needs an LDA step, which is an analysis decision |
| Sentiments | `positive`, `neutral`, `negative` | records with a non-zero score per polarity |
| Languages | `asr_language` | available |
| ManifestoBERTa | — | **no source**: `manifestoberta_predicted_class` has no counterpart in the reprocessed pipeline |
| Statistics | `country`, `political_preference`, `source_type` | counts per grouping column |
| Themes | child `postprocess_themes` | top labels, plus counts over time |
| Persons | child `postprocess_entities` | top labels, plus counts over time |

## Filters

Available: country, political preference, source type, language, duration, date range (the end date is a whole
day), free-text search **within a named column** — searching every column would silently match identifiers.
Unavailable because their source columns do not exist: ManifestoBERTa class, LDA topic, and the legacy
model-free entity filter.

## Not implemented on purpose: the write path

The legacy workbench records review decisions — `video_checked`, `delete_video`, `dubious_video`, `rerun_llm`,
`rerun_ocr`, `rerun_whisper`, `cut_video`/`cut_at`/`cut_keep`, `split_video`/`split_at`, `new_themes`,
`new_persons`, `researcher_note` — in MongoDB. The reprocessed app is read-only by contract (its unit points at
a read-only snapshot), so a decision is needed first: a MongoDB review collection (legacy behaviour, new write
path), append-only review events in the private repository, or no write path in this iteration.

This increment is the third option: the reading half is delivered, and nothing invents a second place where
research decisions live. See #263 §4.
