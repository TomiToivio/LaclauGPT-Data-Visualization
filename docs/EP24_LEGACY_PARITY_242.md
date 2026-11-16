# Legacy parity record for the EP24 researcher dashboard (#242 §3)

What the legacy `:8501` dashboard did, what the deployed researcher dashboard does with the same
question, and what it deliberately does not do. Written against the legacy source
(`TomiToivio/ep2024_dashboard`, `dashboard.py`, 4 830 lines: 9 per-video tabs, 9 aggregate tabs,
43 `st.plotly_chart` calls, 5 `st.metric` tiles, 13 sidebar controls) and verified against the
running service at `http://100.115.95.109:8502/`.

The earlier analysis record is `docs/EP24_LEGACY_FEATURE_MATRIX.md`; this is the #242 acceptance
record. Where they disagree, this one is newer.

## Verdict in one line

Every legacy question that this cohort can answer is answered, in the legacy palette and typography
(`LEGACY_COLORWAY` in `live_steps_app.py`); two legacy surfaces have no honest counterpart in this
pipeline and are named here rather than imitated.

## Per-video surfaces

| legacy tab | status | in the new app | note |
|---|---|---|---|
| Metadata | preserved | Record browser — identity block | country, platform, author, dates, duration |
| Whisper | preserved | Record browser — transcript and translation | original language and translation side by side |
| OCR | preserved | Record browser — on-screen text per frame | verbatim, with frame timestamps |
| Multimodal | preserved | Record browser — frame and video observations | frame VLM and video VLM kept apart |
| Summary | preserved | Record browser — multimodal summary | plus the producer's quality status |
| Populism | improved | Discourse · DNA — step 6 | full Laclaudian coding (signifiers, demands, identities, antagonism, affect) with the formula conditions, abstention reason and counter-evidence; legacy had the formula score only |
| Themes | preserved | Record browser — themes; Aggregates — theme counts | producer-coded, not inferred |
| Persons | partial | Aggregates — entity counts | this export has no separate persons column; person-like entities come from the entity field |
| Report Problems / Researcher Notes | replaced | Problems tab + `researcher_note` in the export | the deployment is **read-only**: it surfaces every non-ok stage with the producer's reason and carries existing notes into exports, but writes nothing back to canonical records |

## Aggregate surfaces

| legacy tab / chart | status | in the new app | evidence |
|---|---|---|---|
| Frequency · *Recording Frequency by Political Preference* | preserved | Legacy charts | bar of counts; denominator caption |
| Frequency · *Video Release Timeline* | preserved | Legacy charts | line by recording month, split by country |
| Statistics · *Video Duration Distribution (violin)* | preserved as distribution | Legacy charts | histogram of seconds; blanks dropped, never zero-filled |
| Statistics · *Total Video Duration by Political Preference* | preserved | Legacy charts | hours per group + count of videos without a duration |
| Statistics · *Videos by Country, Political Preference & Source Type* | preserved | Legacy charts | three-level sunburst |
| Statistics · *Political Preference Distribution* | preserved | Legacy charts | the frequency chart *is* the distribution |
| Statistics · *Dataset Coverage Gauges* | moved, deliberately | Steps & coverage; Legacy charts | a measured table per stage with denominator and percentage, instead of a gauge that hides *which* records are missing |
| Entities · *Top 20 entities* | preserved | Aggregates | member counts from the producer's entity field |
| Themes · *Top 20 Themes* | preserved | Aggregates | as above, theme field |
| Sentiments · *Top positive / neutral / negative* | preserved | Aggregates — sentiment totals | mention counts per producer-coded target |
| Languages · *Language Distribution*, *by political preference* | preserved | Legacy charts | language × preference bars |
| ManifestoBERTa · class distribution, classes by preference | **not reproduced** | — | no such model output exists in this pipeline. A stand-in would be a different variable under the same name, which is exactly the substitution the issue forbids |
| Persons · *Top 30 Persons* | partial | Aggregates | no persons field; entity browsing covers what the export carries |
| Topics · *Top 30 topics* | partial | Aggregates — themes; Stage explorer | topic-like fields are the theme and entity codings |
| — | **new** | Discourse · DNA, Network · SNA, Stage explorer, Export | steps 6–8 have no legacy counterpart |

## Design language

The deployed app sets Plotly's default template to the legacy colourway
(`#6C63FF #00C2A8 #FF6B8A #FFA94D #4DABF7 #B197FC #63E6BE #F783AC #FFD43B #74C0FC`), `#FFFFFF` paper,
`#FAFBFF` plot area and Inter/Segoe UI 13 px. Verified by reading `plotly.io.templates.default` in the
app process (`ep24_legacy`).

## How this was verified

1. `AppTest` against the real artifact directory: 13 tabs render, no exceptions, 29 charts.
2. `scripts/ep24/verify_researcher_dashboard.py --url http://100.115.95.109:8502` — 16/16 checks,
   including the served commit and a clean served tree.
3. The legacy chart list was extracted from `dashboard.py` itself (titles and `st.tabs` calls), not
   from memory of the old dashboard.

## What parity still cannot claim

- The live legacy `:8501` endpoint named in the issue was not re-audited for this cohort; the
  comparison is against the legacy **source**, which is the stronger reference but not a screenshot
  diff.
- A researcher who relied on writing annotations inside the legacy UI must keep doing that
  elsewhere: this deployment reads canonical records and writes nothing.
- ManifestoBERTa users get no direct replacement.
