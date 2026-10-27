# EP24 legacy → reprocessed feature matrix (#195, #306 §5)

**Status: analysis record.** What the legacy `ep2024_dashboard` does, what the
reprocessed explorer does, and what the new one does **not** yet replace. Written
because "the new dashboard is better" is an assumption until the two are compared
feature by feature.

Legacy source: `TomiToivio/ep2024_dashboard`, `dashboard.py` (4,831 lines, 43 Plotly
charts, 5 `st.metric` tiles, 9+9 tabs, 37 sidebar controls, one CSV download).

## 1. Legacy: what a researcher could actually do

**Per-video inspection tabs**

| tab | content |
|---|---|
| Metadata | source identity, country, platform, preference, timestamps |
| Whisper | transcript and translation, side by side |
| OCR | per-frame OCR text |
| Multimodal | per-frame LLM analysis |
| Summary | LLM summary analysis |
| Populism | formula-of-populism analysis |
| Themes | theme assignments |
| Persons | person/actor extraction |
| Report Problems / Researcher Notes | free-text annotation workflow |

**Aggregate analytics tabs**

Frequency · Entities · Topics · Sentiments · Languages · **ManifestoBERTa** ·
Statistics · Themes · Persons

Named visualisations: *Recording Frequency by Political Preference*, *Total Video
Duration by Political Preference*, *Videos by Country, Political Preference &
Platform*, *Video Release Timeline*, *Video Duration Distribution (Violin Plot)*,
*Dataset Coverage Gauges*, *Political Preference Distribution*.

## 2. Reprocessed explorer: what exists now

| surface | coverage |
|---|---|
| Multimodal · Steps 0–5 | ASR/OCR/translation, frames, video analysis, summary, postprocess |
| Laclaudian discourse · Step 6 | status, abstention, structured coding |
| DNA · Step 7 | statements, unresolved/uncertain counts |
| Social network · Step 8 | nodes, edges, edge-type filter, node table |
| Combined multilayer | cross-step view |
| RDF · Step 9 | resources |
| Evidence inspector | source record drilldown from any view |
| Export manifest and stage coverage | provenance, per-step counts, dropped columns and why |
| Legacy / QA | legacy comparison surface |
| Filters | country scope, platform, language, discourse status, date, video id substring |
| Export | filtered video table (CSV) |

## 3. The matrix

| capability | legacy | reprocessed | verdict |
|---|---|---|---|
| Per-video transcript + translation | yes (Whisper tab) | inside Steps 0–5 | **preserved** |
| Per-frame OCR and LLM analysis | yes | inside Steps 0–5 | **preserved** |
| Summary inspection | yes | Step 4 | **preserved** |
| Discourse coding | Populism tab (formula only) | Step 6, full Laclaudian coding | **improved** |
| DNA statements | no | Step 7 | **new** |
| Social network | no | Step 8 | **new** |
| RDF | no | Step 9 | **new** |
| Stage provenance and missingness | no | manifest + coverage | **new** |
| Evidence drilldown from a chart | partial | evidence inspector | **improved** |
| Annotate / report problems | yes, first-class tab | not present in the explorer | **GAP** |
| Aggregate frequency / timeline / duration charts | yes, 43 charts | not present | **GAP** |
| Coverage gauges | yes | per-step coverage in the manifest | **moved, less visual** |
| Sentiment aggregates | yes | not present | **GAP** |
| Language aggregates | yes | filter only, no aggregate view | **GAP** |
| ManifestoBERTa | yes | not present | **GAP** |
| Person/entity browsing | yes (Persons tab) | entity data in rows, no browse view | **partial** |

## 4. What this means

The two dashboards are **not versions of the same thing**. Legacy is an *analytics*
dashboard: aggregate distributions, sentiment, language, and a strong per-video
inspection path. The reprocessed explorer is an *observability* dashboard: what ran,
what failed, what evidence supports each claim, and what is missing.

Neither supersedes the other, and the matrix above is the argument against retiring
legacy until the analytics half is rebuilt on the new export. The gaps that matter most
are the four with no equivalent at all: **annotation/reporting**, **aggregate analytics**,
**sentiment**, and **ManifestoBERTa**.

## 5. Side-by-side comparison: how the join works

- Legacy rows key on `video_id` / `allas_filename`.
- Reprocessed rows key on `record_id`, namespaced `video:<allas url>` so a video export
  and an ingest export can never be joined by accident (#205).
- The stable join is therefore **`allas_filename` ↔ the URL inside `record_id`**, not
  `video_id`, which differs between pipeline generations.

A side-by-side view should declare which generation each pane comes from, refuse to
render a comparison when the join fails, and show the count of unmatched rows on both
sides - an unmatched comparison silently looks like agreement.

## 6. Recommended order

1. **Annotation / report-problems** - the only workflow that produces human labels, and
   therefore the input to every quality claim in #306 §3.
2. **Aggregate analytics** on the new export (frequency, timeline, duration, coverage).
3. **Sentiment and language aggregates**.
4. **ManifestoBERTa**, if it is still wanted at all - it is the most expensive and the
   least used of the legacy tabs, and that is a decision, not a default.
