# Legacy / Specialized dashboards

Issue #21 deliberately keeps the EP24-derived **pledge** and **art** datasets outside the complete modern LaclauGPT analysis pipeline. These are archival/specialized research instruments with their own privacy-safe adapters and a shared `legacy-view-v1` interchange contract.

## Architecture

```text
private CSV/DuckDB/runtime input
  -> Python deterministic adapter
     - preserve raw values
     - validate/normalize legacy fields
     - explicit provenance
     - no political inference
  -> private runtime view_model.json + provenance.json
  -> R research twin / aggregate QA / static figures
  -> JavaScript linked research + exhibition views
```

Real row-level data, embeddings, projections and exports stay under ignored runtime/output paths. The repository contains only code and synthetic fixtures.

## Pledge dashboard

`scripts/legacy/pledge/preprocess.py` preserves grievance text and token raw values, creates normalized long-form token rows, and makes political metadata provenance explicit:

- `observed`: present in the source record;
- `legacy_derived`: supplied by a historical repair field and never presented as source-observed;
- `missing`: neither source-observed nor historically supplied.

The JavaScript `Provenance Lens` defaults to observed-only. The research ledger exposes the status explicitly. `aggregateTemporal()` provides the deterministic temporal backbone for Discourse Weather; token rows support Topic Loom and future semantic runtime projections without putting real embeddings in Git.

## Art dashboard

`scripts/legacy/art/parse_analysis.py` parses Markdown sections into concept families while retaining `raw_term`, `canonical_term`, source identity, line number and normalization provenance. `preprocess.py` builds documented country-concept edge weights.

`web/legacy/art/constellation.js` provides the maintained constellation seed with Research / Exhibition and pause/reduced-motion controls. The UI states that orbital/constellation positions are decorative. If private runtime semantic coordinates are later supplied, those must be marked analytical and accompanied by projection metadata and R stability diagnostics.

## Shared interchange

All view models include `contract_version = legacy-view-v1`. The public synthetic golden fixture lives at `tests/fixtures/legacy_golden.json`. Private runs conventionally write:

```text
<runtime-output>/view_model.json
<runtime-output>/provenance.json
<runtime-output>/r/*.csv|*.png
```

Derived fields should retain source field, observation/derivation status, normalization/parser rule and contract version. Original inputs are never overwritten unless the researcher explicitly uses `--overwrite` for generated outputs.

## R analytical twin

`scripts/legacy/pledge/analyse.R` independently checks alignment provenance and writes a provenance diagnostic figure/table. `scripts/legacy/art/analyse.R` independently constructs the country × concept descriptive matrix and a static heatmap. These are descriptive research outputs, not rankings or political evaluations.

## JavaScript

`web/legacy/pledge/pledge.js` contains filtering, provenance lens, ledger and temporal aggregation primitives. `web/legacy/art/constellation.js` contains the shared concept graph and accessible research/exhibition renderer. Both consume the Python contract rather than re-parsing private source data in browser code.

## Running

```bash
python -m scripts.legacy.pledge.preprocess /private/pledge.csv data/legacy/pledge
python -m scripts.legacy.art.preprocess /private/art.csv data/legacy/art
Rscript scripts/legacy/pledge/analyse.R data/legacy/pledge/view_model.json data/legacy/pledge/r
Rscript scripts/legacy/art/analyse.R data/legacy/art/view_model.json data/legacy/art/r
npm run test:legacy
pytest tests/test_legacy_specialized.py
```

The R scripts require `jsonlite` and `ggplot2`. MongoDB, Redis and Allas are intentionally not required.

## Methodological boundaries

Do not infer political alignment, ideological quality, actor performance or recommendations in Visualization. Do not interpret graph prominence, decorative geometry, projection distance or animation as discourse-theoretical evidence. Drill-down to private source evidence remains a runtime researcher action.
