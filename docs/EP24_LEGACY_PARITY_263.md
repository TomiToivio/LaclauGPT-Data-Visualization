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

**Where the date comes from.** The export's `created_at` and `timestamp` are empty for all 1,500 FI/PL/PT
records, but the video id carries the date: `HEPP24-FI-CR-IG-20240521-1027000` is study, country, preference,
platform, `YYYYMMDD`, then a sequence. `add_created_at()` fills a blank `created_at` from the date part (all
1,500 parse, covering 2024-05-20 .. 2024-06-16) and leaves a real value untouched, so a backfilled export
takes over silently.

Precision is **one day**, deliberately. The trailing field is not a clock: it takes 180 distinct values from
`1010000` to `4080000` and 366 of them cannot be any `HHMMSS` (minute 90, second 95), so it behaves like a
per-session sequence. Deriving a time of day would fabricate one. The frame records how many values it filled
(`frame.attrs["created_at_derived"]`) and the sidebar says so, because a derived timeline must not be read as
a measured one.
Unavailable because their source columns do not exist: ManifestoBERTa class, LDA topic, and the legacy
model-free entity filter.

## How a record tab tells the truth

Three states are kept apart, because collapsing them is how a tab lies:

| state | meaning | what the tab says |
| --- | --- | --- |
| carried | this record has output for the field | the value, as text |
| absent | **the export does not carry the column at all** | the fields it looked for, by name |
| empty | the column exists, this record has no output | "no output for this record — an absence of output, not a finding that the video has none" |

Consequences worth naming:

- **Cell values are rendered as text, not markdown.** They are transcriptions and model output derived from
  corpus content; a transcript containing markdown must not be interpreted by the page, and a structured
  cell is projected through `ep24_presentation.readable()` so producer keys cannot be published just
  because a tab displays the field.
- **`platform` is presented as a derivation** (`source_type` + `account_type`) when the export has no
  `platform` column, rather than as an observation.
- **Child rows are matched on either identifier dialect** — `source_key` in the delivered export,
  `parent_record_id` in the older one. A loader that knows only one of them renders Themes and Persons
  empty against a correct export.
- **Counts are per video, not per mention.** The child tables hold one row per mention, so a plain value
  count answers "how often was this said" while the column claims records. Every entity/theme figure is
  deduplicated on `(source_key, label)` and labelled `videos`, with the filtered frame as its denominator
  and `source_key` as its identity rule.

## Not implemented on purpose: the write path

The legacy workbench records review decisions — `video_checked`, `delete_video`, `dubious_video`, `rerun_llm`,
`rerun_ocr`, `rerun_whisper`, `cut_video`/`cut_at`/`cut_keep`, `split_video`/`split_at`, `new_themes`,
`new_persons`, `researcher_note` — in MongoDB. The reprocessed app is read-only by contract (its unit points at
a read-only snapshot), so a decision is needed first: a MongoDB review collection (legacy behaviour, new write
path), append-only review events in the private repository, or no write path in this iteration.

This increment is the third option: the reading half is delivered, and nothing invents a second place where
research decisions live. See #263 §4.

## The data the dashboard reads

The workbench reads the released export in place, not a rebuild: `fiplpt_500_20261115_release` on the host,
verified against its `manifest.json` by `scripts/ep24/verify_served_export.py` (28 files, zero
disagreements). See `docs/EP24_SERVED_EXPORT_VERIFICATION.md` — before that check existed the host served a
flat `combined.csv` build that matched no committed file, and the manifest was three sidecars short of its own
tree.
