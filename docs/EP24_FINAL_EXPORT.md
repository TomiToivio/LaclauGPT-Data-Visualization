# EP24 final-result export — issue #195, Part 1 implementation

## Scope and delivery status

Tomi explicitly requested this EP24 work in #195. It is an isolated exception to
this repository's AI26-only default policy, reusing `ep24_pipeline.py`'s field
contract. AI26 entrypoints and existing deployment services are unchanged. The
exporter is portable with that small consumption contract to an EP24 repository.

This implements the export code, **not the completed real-data delivery**. The
implementation was checked against producer revision
`c3ffc569dea1b2c008000075f23bbea46ef8dfc8`, including its stage contract, canonical
schema, pipeline-column configuration, checkpoint writer, orchestration state,
Step 8 writer and RDF writer. The producer's Python stage contract still omits
new Step 8/9 fields; this exporter supplements it from the actual writers and
`config/ep24_pipeline_columns.json`.

The current execution workspace could read GitHub repositories, but its TCP
connection to the configured MongoDB endpoint failed. No SSH credentials for the
requested deployment hosts were available. Consequently no real checkpoint,
FI/PL/PT coverage, live export, UI demonstration or new deployment was verified.
Do not close #195 or describe a synthetic test export as the requested demo.

Part 2 remains gated on an inspected, permissioned three-country export. The
existing reprocessed app expects flat producer rows; this export's JSONL envelope
requires an explicit adapter before connecting it to that UI. Do not point that
app at the scalar CSV and assume structured results survived. The new dashboard,
legacy visual audit, all-page UI tests and distinct deployed service remain work
to complete after the data gate.

## Run on an authorized research host

```bash
python -m pip install -e '.[dev]'
python scripts/ep24/export_visualization_data.py \
  --countries finland poland portugal \
  --input finland="$FI_CHECKPOINT" \
  --input poland="$PL_CHECKPOINT" \
  --input portugal="$PT_CHECKPOINT" \
  --output "$LACLAUGPT_PRIVATE/analysis/ep24_reprocess/visualization_exports/run-001"
```

Each input is an explicit cumulative `.csv`, `.jsonl`, `.sqlite3`, `.sqlite` or
`.db` snapshot. SQLite defaults to the producer's `records` table; use
`--sqlite-table` for an intentionally selected alternative. CSV fields are read
as strings, including leading-zero video IDs. Never choose an old stage file
just because its filename sorts last. Confirm the checkpoint provenance first.

Optional direct Mongo source, on a host with authorized database connectivity:

```bash
python -m pip install -e '.[remote]'
python scripts/ep24/export_visualization_data.py \
  --mongo-database "$EP24_DATABASE" \
  --mongo-uri-env LACLAUGPT_MONGODB_URI \
  --output "$LACLAUGPT_PRIVATE/analysis/ep24_reprocess/visualization_exports/run-002"
```

Load the URI privately into the named environment variable. Never put it in the
command line or a public log. The adapter only calls `find` on the three
`laclaugpt_ep2024_reprocess_<country>_dataframe` collections. Use a read-only DB
account. It does not claim records or modify stage state. The collections are
read sequentially, not as a cross-country transactional snapshot; avoid concurrent
pipeline changes for a reproducible release.

Outputs are private research data, including transcripts and researcher notes.
They belong in `LaclauGPT-Private`, as requested, under the example relative
export directory above. This is **not** an anonymizer or a public-release tool.
Apply private repository LFS policy to large outputs. No real export has been
committed by this change. Credentials remain in their authorized private runtime
configuration, not in these bundles.

Use a fresh directory for every refresh. The exporter refuses to overwrite an
existing export. It writes `manifest.json` last. Only a directory containing a
verified manifest may be promoted as the dashboard's active snapshot. Check the
manifest hashes and QA before switching. Never replace the legacy services.

## Export contract and identity

The JSONL envelope contains `source_key`, `fields`, `stages`, and `provenance`.
`fields` retains producer names and values; it is a lossless allowlisted
**view projection**, not a new producer schema. The cumulative source is unchanged.

The view join key is the percent-encoded tuple country/dataset/platform/video ID.
An absent dataset uses the documented `ep2024_reprocess` namespace. Video IDs
are opaque strings. `_storage_id` and an existing `source_url` are retained as
aliases; neither replaces the country-aware view join key. Missing/invalid video
IDs, missing platform and country disagreement are quarantined in `qa.json`.
Source URLs are never fabricated. Conflicting rows for one key are all excluded;
identical final projections are collapsed with all input row locators retained.
Different `_storage_id` values for one video therefore trigger a visible conflict.

`provenance` binds each record to its source snapshot hash and 1-based data-row
ordinal (CSV header excluded). Source hashes and row counts are also in the
manifest. File sources are hashed as bytes; Mongo sources hash sorted retrieved
records. `--producer-revision` records an actual known run revision; otherwise it
remains null. `mapping_producer_revision` only identifies the code used to audit
the exporter mapping. Model/prompt/schema versions remain on individual records.

For deterministic reruns, use identical snapshots and a fixed ISO timestamp in
`--exported-at`. The output includes hashes of every bundle member except the
manifest itself. Input ordering is retained in provenance row ordinals.

## Files and field mapping

| File | Meaning |
| --- | --- |
| `combined.jsonl`, country `.jsonl` | Final fields with native nested JSON, stage reports, source provenance |
| `combined.csv`, country `.csv` | Scalar identity, text, status, quality and version fields |
| `combined.md`, country `.md` | All available final fields, with researcher annotations separate from model output |
| Child-table `.jsonl` / `.csv` | Entities, themes, sentiment targets, discourse items, DNA statements, SNA nodes/edges |
| `dictionary.json` | Exact allowlist by step, researcher/structured fields, omitted field names and policy |
| `qa.json` | Invalid IDs, country/platform errors, malformed JSON and duplicate diagnostics |
| `manifest.json` | Sources, revision attribution, hashes, counts, per-country/per-stage status coverage |

Every child row has a stable content-based ID, `source_key`, country, producer
field path and array index. JSONL retains the entire original item, including
nested evidence and uncertainty. Child CSV exposes scalar item properties only;
nested evidence remains in JSONL and the Markdown report. Repeated identical
items have distinct occurrence IDs. Discourse arrays keep their producer category
under `field`; the exporter does not reinterpret every item as a discourse claim.

| Step | Retained final results / interpretation |
| --- | --- |
| 0 | Source identity/metadata and separately identified researcher annotations |
| 1 | ASR, translation, OCR, frame reference/time, backend/model, preprocess quality |
| 2 | Final frame analysis, quality, model and context digest |
| 3 | Final temporal narrative/structured result, scroll flags, quality, model/prompt provenance |
| 4 | Final fused summary and quality reason |
| 5 | Entities/themes/targets, canonical resolutions and unresolved cases; no human/model merge |
| 6 | Laclau structured coding, Markdown, abstention, model/prompt provenance and reported status |
| 7 | DNA statements and evidence, Markdown, uncertainty counts and provenance |
| 8 | Nodes, edges, upstream metrics, separate Castells interpretation, schema/status and provenance |
| 9 | Per-row RDF URIs, schema and reported export status |

All fields outside the allowlist are omitted by default. Specifically excluded:
raw model responses, prompts, RAG/codebook/memory context, local/remote working
paths, tensors, runtime counters, transient claims, backend URIs and arbitrary
`metadata`. Source `frame_file`/`allas_filename` references are retained because
they are evidence references, reinforcing that this bundle is private. The
`_pipeline` object is reduced to per-stage status, completion time and error type;
worker/claim/lock details are excluded.

CSV formula-like strings are prefixed with an apostrophe for safe spreadsheet
opening; JSONL preserves their original values. Human CSV intentionally omits
nested JSON cells. Malformed structured values remain inspectable in JSONL and
are reported in QA rather than silently replaced by an empty list.

## Completion semantics and remaining gates

Stage reports keep result status separate from execution status and field
availability. Neither output presence nor process success means validated
interpretation. Shared `processing_status` is not attributed to Step 5 because
other stages also write it. `no_evidence`, `warning`, failure and retry remain
explicit. Absent stages remain `not_exported`; empty lists remain explicit lists.
RDF files do not mark every row successful.

A zero exit code means requested countries have usable exported rows, **not**
that every stage completed or findings are valid. Missing requested countries
return exit code 2, with the partial export and coverage report preserved.

Before delivery: inspect the real checkpoint and Mongo schema, resolve any mapping
or duplicate findings, verify coverage and a record from each country, and add
explicit RDF artifact copying/validation with row provenance. The initial exporter
does not copy TTL/NT artifacts or normalize triples. Add the dashboard adapter,
legacy-compatible UI, all requested graph interactions, >=1,000-record UI tests,
private screenshot evidence and a distinct authenticated service deployment. The
Part 1 real-data gate and Part 2 acceptance checklist remain open.

## Verification

```bash
python -m pytest -q tests/test_issue195_export.py
python scripts/check_public_tree.py
python -m ruff check .
python -m pytest
```
