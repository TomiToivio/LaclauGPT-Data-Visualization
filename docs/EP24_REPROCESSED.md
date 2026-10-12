# EP24 Reprocessed dashboard (issue #177, foundation)

A **separate** researcher-facing Streamlit entrypoint. Existing AI26 entrypoints, navigation and environment are unchanged. The implementation is **read-only** and does not require MongoDB, Redis, a GPU, or Roihu access.

## Start on Pouta or locally

```bash
python -m pip install -e .
export LACLAUGPT_VIS_ANALYSIS_DATA_DIR=/private/ep24/export
streamlit run src/laclaugpt_visualization/ep24_reprocessed_app.py --server.address 127.0.0.1 --server.port 18503
```

Forward port 18503 through SSH when accessing a Pouta host. Keep real research data outside Git, behind authenticated network access, and never publish Streamlit directly. The app loads the first available exported `combined.csv`, country CSV, `records.csv`, `records.jsonl`, or local SQLite (`combined`/`records`/`annotations` table). Exported `graph.ttl` / `graph.nt` files are inspected separately.

### Verified mapping (upstream `ep24_stage_contract.py`, 2026-10-12)

| Step | Field examples | Important distinction |
|---|---|---|
| 0 | `video_id`, `allas_filename`, `_storage_id`, `country`, `source_type` | Presence does not prove ingestion QA |
| 1 | `preprocess_status`, `asr_transcript`, `ocr_1`, `frame_file` | Keyframe at source t=1s |
| 2 | `frame_analysis_status`, `frame_analysis_1` | Evidence is VLM-produced |
| 3 | `vllm_video_status`, `vllm_video_analysis` | Video narrative and structured output |
| 4 | `summary_analysis`, `summary_quality_status` | Multimodal summary |
| 5 | `postprocess_entities`, `postprocess_themes`, `ep24_entity_resolution_json` | Distinct from researcher `entities` / `themes` |
| 6 | `laclau_status`, `laclau_structured_json`, `laclau_abstention_reason` | Do not infer theory from frequency |
| 7 | `dna_status`, `dna_statements_json` | Actor–concept coded statement, not actor tie |
| 8 | `sna_edges_json` | Actor–actor only with a quote and explicit relation type |
| 9 | `graph.nt`, `graph.ttl` | Filesystem RDF export, **not** per-row status |

These are **projection contracts** only. Field aliases, schema variations, nested JSON and old exports may require additional normalization after validating real exports.

### Supported today

Stage 0–9 visibility and raw inspection, filtered record browsing, separate Step 6/7/8 views, evidence-table-backed multilayer graph, basic source/actor/concept/DNA/SNA typed connectors, bounded plotting, simple QA, and local RDF preview. `ep24_reprocessed.py` is pure and importable without Streamlit.

### Known gaps before #177 can close

- No guaranteed per-record Step 9 completion (the current export contract is file-based).
- Country CSVs are not yet assembled as a combined data source; `combined.csv` is preferred. There is no DuckDB adapter.
- Full upstream statement schemas, corpus-wide entity resolution and alias collisions need real-export tests; the first graph deliberately never guesses joins from co-mentions.
- No interactive node-click cross-filtering, time slider, actual source media preview, legacy-side-by-side diff, RDF URI → analytical entity lookup, downloadable graph exports or advanced performance benchmarks.
- The graph is inspectable and typed but the initial visualization is bounded to 500 edges and uses a static Plotly network; filter/editing is table-led.
- Neither a successful process exit nor presence of a JSON field is sufficient to claim validated analysis. Status strings are kept explicit.

## Refresh

Atomically replace or synchronize the **private** export root after a Roihu run; refresh the app page. Never commit source media, credentials, private annotations or the country CSVs. No re-deployment is necessary for data-only updates.

## Tests

```bash
pytest -q tests/test_issue177_ep24_reprocessed.py
```
