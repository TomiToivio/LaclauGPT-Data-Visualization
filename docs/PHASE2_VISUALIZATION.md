# Phase 2 visualization layers

Issue #169 activates researcher-facing Phase 2 inspection without moving analysis semantics into Visualization.

## Research layers

The workbench keeps the scientific objects explicit instead of folding them into one generic graph:

1. **Source / multimodal evidence**: canonical source records, transcripts, OCR, frames and exact evidence selectors.
2. **DA**: the existing Laclaudian discourse-analysis views from Phase 1.
3. **DNA**: `pages/2_DNA.py` consumes the Analysis-owned `laclaugpt.multimethod.v1` statement/projection contract. Actor-concept, actor-actor and concept-concept projections remain upstream analytical products.
4. **SNA**: `pages/3_SNA.py` consumes an explicit Analysis `NETWORK` product through `sna.py`. It displays ordinary node/edge structure and upstream metrics without renaming centrality as a theoretical construct.
5. **RDF**: `pages/rdf_explorer.py` consumes the Analysis-owned RDF service and preserves exact URIs, stage/type distinctions, provenance and evidence drill-down.

Visualization never creates a replacement DNA ontology or RDF vocabulary.

## Input contracts

### DA

Input is the canonical Analysis/Visualization record. Existing Phase 1 behavior remains unchanged.

### DNA

Input is the DNA-compatible Analysis artifact already consumed by `dna_views.py` and `dna_page.py`. The direct statement view preserves actor, concept, stance/qualifier, time, source and evidence identity. Projected networks must carry their projection and weighting semantics.

### SNA

Input is a portable `DataProduct(kind="network")`-shaped JSON object, or a direct JSON object with `nodes` and `edges`. Optional `measures` are displayed exactly as supplied. Missing measures are shown as missing; the UI does not compute substitutes.

Recognized node typing is intentionally open and supports human and artificial communicators such as person, organization, government, party, media, movement, platform, llm, ai_agent, bot, algorithmic_system, device and unknown when supplied upstream.

### RDF

RDF comes from the canonical Analysis RDF provider. The view must preserve the stage chain:

```text
source
 -> multimodal/frame evidence
 -> descriptive summary
 -> Laclaudian DA
 -> DNA statement/projection
 -> SNA graph/metric/community
 -> review/provenance
```

## Provenance and evidence

Every layer should retain the shortest available path back to `source_url` and exact evidence/provenance identifiers. Missing evidence is rendered as missing, never synthesized.

## Filters

DA keeps the existing Phase 1 filters. DNA exposes statement/projection filters. SNA exposes node/actor type, platform, project, dataset, date range and discourse concept/formation filters plus bounded node/edge inspection. These filters only inspect fields already supplied by Analysis; missing metadata is never inferred or synthesized. RDF exposes provider-backed type, explicit research-stage, provenance and query filters. The stage filter passes Analysis-owned labels through unchanged; Visualization does not infer a stage from RDF class names.

## Exchange and interoperability

DNA-compatible exports, GraphML, GEXF and RDF are canonical Analysis exports. Visualization makes those exports discoverable rather than rebuilding their semantics. DNA additionally has the existing GraphML/GEXF/node+edge export helpers. SNA exposes visible node/edge CSV tables and shows canonical upstream export references when the NETWORK product metadata contains `exports`.

DATS remains document/annotation/code/entity exchange. It is not described as an SNA method.

## Missing and uncertain data

Absence is not zero. Missing projections, metrics, communities, timestamps, evidence or RDF stages stay visibly absent. Provisional/model-produced annotations keep their review/uncertainty state.

## Scientific boundary

Degree, betweenness, closeness, PageRank, eigenvector centrality, communities and components are conventional network measures. They may be interpreted later in Castells/Esposito-informed research, but the UI does not label any numeric measure "network power", "programming", "switching", "hegemony", "nodal point", "equivalence" or "antagonism".

## Tests

- existing DNA interoperability and export tests cover statement/projection semantics and GraphML/GEXF;
- `tests/test_phase2_sna_page.py` covers NETWORK contract normalization, rejection of non-network inputs, and upstream-only actor/platform/project/dataset/date/discourse filtering;
- `tests/test_issue101_graph_api.py` enforces that both DNA and SNA are Phase 2 graph layers;
- the shared graph contract tests require `multimodal` and `summary` to remain distinct stage layers, and the RDF explorer exposes the provider-owned stage/layer field for filtering and inspection;
- existing RDF tests cover read-only provider behavior, bounded graphs and evidence paths;
- existing Phase 1 tests remain the regression gate.
