# EP24 FI/PL/PT 500-video dashboard — legacy parity audit (#242)

Audited 2026-11-16 for #242's "legacy parity + new capabilities" requirement. This is the
`legacy feature → new implementation → verification` matrix the issue asks for, and it says plainly
which rows are verified and which are not.

## What was audited, and what could not be

| Source | Access | Status |
|---|---|---|
| Legacy dashboard source `ep2024_dashboard/dashboard.py` (213 KB, 4 746 lines) | full read on the host that serves it | **audited** |
| Live legacy app `http://195.148.31.227:8501/` | reachable, but renders a login gate; no credentials used | **not audited** — the authenticated views were never observed |
| New app `src/laclaugpt_visualization/ep24_reprocessed_app.py` | source + `AppTest` against the real 1 500-record export | **audited** |
| New researcher app `src/laclaugpt_visualization/live_steps_app.py` (#244) | source + the #244 verifier's 16/16 checks | **audited** |

The live legacy app is password-gated, so this matrix compares the **legacy source's** feature set
with what the new apps implement. Anything that depends on how the authenticated legacy page actually
looks or behaves is marked *unverified*, not *parity*. That limitation is #242's own instruction
("Live access may be unavailable: record that limitation, do not claim parity without verification").

## Per-video views

Legacy: nine tabs per video — Metadata, Whisper, OCR, Multimodal, Summary, Populism, Themes, Persons,
Report Problems / Researcher Notes.

| Legacy view | New implementation | Status |
|---|---|---|
| Metadata | record header in the evidence inspector (`ep24_reprocessed_app`, "Evidence inspector") | parity |
| Whisper transcript + translation | `asr_transcript`, translated text in the inspector | parity |
| OCR (frame 1) | `ocr_1` shown as its own stage field | parity |
| Multimodal LLM analysis (frame 1) | stage 2 (`frame_analysis_1`) inspector field | parity |
| Video-level VLM observations | stage 3 (`vllm_video_analysis`) | parity, **new capability** (legacy had frame 1 only) |
| LLM summary | stage 4 (`summary_analysis`) | parity |
| Formula of populism | stage 5 (`postprocess_*`) | parity |
| Themes | stage 5 themes | parity |
| Persons / entities | stage 5 entities + typed child table (`entities.csv`) | parity, **new**: normalized child table |
| Discourse statements (Laclau) | stage 6 + `discourse_items.csv` | **new capability** (legacy had no step 6) |
| DNA statements + graph | stage 7, `dna_statements.csv`, bipartite actor–concept graph with stance + quotation | **new capability** |
| SNA actor–actor network | stage 8, `sna_nodes.csv` / `sna_edges.csv`, evidenced ties only | **new capability** |
| RDF / knowledge graph | stage 9, status + file inspector when the artifact exists | **new capability**, currently `not_exported` for all three countries |
| Report Problems / Researcher Notes | researcher notes are a separate private table, not written into the export | **not implemented** in the new app — recorded as an open gap |

## Corpus-level views

Legacy aggregate tabs: Frequency, Entities, Topics, Sentiments, Languages, ManifestoBERTa, Statistics,
Themes, Persons — about twenty plotly figures (bar, violin, bubble, timeline, gauges, word clouds).

| Legacy aggregate | New implementation | Status |
|---|---|---|
| Number of videos / recording frequency / duration distribution | coverage + corpus views in the researcher app (#244), per-country counts | parity |
| Videos by country, platform, political preference | country/platform selectors and distributions | parity (political preference only where the export carries it — `unverified` for the legacy coding) |
| Video release timeline | timeline view | parity |
| Dataset coverage gauges | stage-coverage table with per-country denominators (`coverage_rows`) | **replacement**, deliberately: a gauge hides which stage is missing; the table names it |
| Top entities / entity word cloud | entity child table + counts | parity for counts, **no word cloud** (word clouds are not an evidenced aggregate) |
| Topics | stage 5 themes | parity |
| Sentiments / sentiment targets | `sentiment_targets.csv` | parity, where the producer emitted it |
| Languages / Whisper language | `asr_language` filter | parity |
| ManifestoBERTa | — | **not implemented**: the FI/PL/PT 500-video producer output does not carry ManifestoBERTa fields |
| Statistics | corpus statistics view | parity |

## Cross-cutting requirements from #242

| Requirement | Status |
|---|---|
| Researcher-safe column allowlist, machine fields hidden by default | **implemented** (#244: 75 kept / 51 dropped with reasons; unknown columns excluded) |
| Explicit disclosure of not-run / partial / errored stages | **implemented** in this PR: `coverage_rows` classifies `ok`/`cached`/`output_present` vs `error` vs `not_exported`; a never-produced stage reads "unavailable in this source", never 0 % |
| Evidence behind every aggregate | inspector links each record identity to its own stage outputs; network views carry their quotations |
| No machine-only columns in default UI/exports | **implemented** (#244 allowlist) |
| Glossary / methodological notes / denominators | partial: coverage table carries denominators and the `not_exported` explanation; a fuller glossary is outstanding |
| Legacy styling consistency | **unverified** — the legacy authenticated page was not observed, so "same design language" cannot be asserted |
| Graceful empty stages | **implemented**: absent stages render as unavailable rather than empty charts |

## Open gaps this audit records

1. **Live legacy verification** requires authenticated access to `:8501`; until then, "parity" here
   means feature-for-feature in the legacy source, not in the legacy rendering.
2. **Researcher notes** are not surfaced in the new app.
3. **ManifestoBERTa** is out of reach for this cohort: the producer output has no such columns.
4. **Step 9 (RDF)** is `not_exported` for all 1 500 records, so the RDF views stay on their empty-state
   path until a producer run emits them.
5. **Poland and Portugal step 7** are 6/500 and 48/500: their DNA views are legitimately almost empty,
   and the coverage table now says so instead of rendering a blank panel.
