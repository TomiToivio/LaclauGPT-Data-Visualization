# DATS/DNA visualization interoperability

This repository treats visualization as a review/interpretation layer over explicit analytical objects. Renderer JSON, coordinates and layout state are never the canonical analytical model.

## Contracts

`laclaugpt_visualization.interoperability` consumes the portable objects produced by `LaclauGPT-Data-Analysis`:

- DATS project/document/code/annotation/review-style interchange objects
- `DiscourseStatement`
- `GraphProjection`

The visualization view model preserves construction semantics, filters, temporal scope, producer/tool version, provenance, review state, uncertainty and evidence links.

### DATS

`dats_review_view()` maps DATS documents, code hierarchies, annotations, notes/memos, temporal series and relations into the same Monitor / Researcher Review / Explore data surface used by native LaclauGPT material. Original DATS IDs remain visible as external IDs.

`export_dats_review()` exports reviewed/provisional annotation state without silently upgrading model output. A model-produced annotation remains `provisional_ai=true` while its review state is `PROVISIONAL`.

### DNA/rDNA

`dna_graph_view()` consumes `DiscourseStatement` rows plus a `GraphProjection` descriptor and produces a renderer-neutral `GraphViewModel`. The initial direct view is actor-concept bipartite because it preserves the coded statement relation without inventing extra projection semantics. Agreement/congruence, conflict, concept and temporal projections should be constructed upstream by Data Analysis and passed here with explicit projection/weighting parameters.

Supported exports:

- JSON semantic projection
- GraphML
- GEXF
- node CSV + edge CSV

GraphML/GEXF include semantic metadata so Gephi/visone users can recover what nodes, edges, projection and weights mean. Round-tripping layout coordinates is optional presentation metadata and must not be interpreted as analytical distance.

## Browser adapters

`frontend/plugins/semantic-renderers.js` defines thin adapters for Cytoscape.js and Sigma.js/Graphology payloads. The adapters consume the semantic graph contract and do not define it.

Use Cytoscape.js for medium-sized interactive semantic/discourse networks and evidence-linked selection. Prefer Sigma.js + Graphology for larger WebGL exploration. Layout output belongs to browser/plugin state unless an upstream analytical method explicitly produced coordinates.

For charts, `vega_lite_spec()` generates portable Vega-Lite JSON. Vega-Lite is preferred for ordinary quantitative/time-series charts because the same spec can be produced from Python/R and rendered in the browser. Observable Plot/D3 remain suitable for bespoke timelines, small multiples, maps and views that do not fit Vega-Lite well.

## Python and R

Python adapters remain thin: tabular/view preparation, declarative specs and static/publication rendering are allowed, but substantive network/community/NLP inference belongs in Data Analysis.

Optional reproducible R examples live under `scripts/r/`. They are not core dashboard dependencies. Use `Rscript` or RStudio to create ggplot2/igraph figures from portable CSV/GraphML/Parquet outputs. rDNA/DNA and STM results should be computed in their owning analysis workflow, then rendered here.

## Evidence drill-down

Every imported visual object should preserve the path:

```text
visual element
 -> analytical result / projection
 -> statement or annotation
 -> canonical source record
 -> exact evidence span / transcript / frame
 -> provenance / model / codebook
 -> human review or correction
```

Original DATS/DNA identifiers remain alongside canonical identifiers so researchers can compare and round-trip results.

## Scientific safeguards

The UI and exported semantic metadata must keep these warnings available:

- graph degree != nodal point
- visual centrality != hegemony
- community/cluster != ideological formation
- actor agreement != Laclauian equivalence
- negative/conflict edge != antagonistic frontier by itself
- semantic proximity != equivalence
- topic prevalence != hegemony
- two clusters != polarization without an explicit operationalization
- decorative layout distance != semantic distance

Visual prominence is descriptive. It must not smuggle a discourse-theoretical conclusion into the research process.

## External tools

### Gephi

Export GraphML or GEXF. Keep semantic metadata and node/edge types. Gephi layout/community results are new derived artefacts and should return with their method, parameters and tool version rather than overwrite the source projection.

### visone

Use GraphML or node/edge tables for inspection. DNA -> visone -> LaclauGPT can preserve identifiers and graph structure, but renderer layout and any visone-derived measures require explicit provenance on re-import.

### DATS

Use the normalized DATS interchange profile from Data Analysis. Export researcher corrections and notes where compatible. AI suggestions must stay explicitly machine-generated/provisional until human review.

## Sources

Visualization-specific methodological anchors include:

- DATS Whiteboards / visual qualitative workspace, LREC-COLING 2024, plus DATS/COTA and Annotation Assistant work for human-in-the-loop review.
- Bastian, Heymann & Jacomy (2009), Gephi.
- Philip Leifeld's Discourse Network Analysis methodology and the DNA/rDNA software ecosystem.
- Newman, *Networks*, for network/projection interpretation.
- Traag, Waltman & van Eck (2019), Leiden, especially the distinction between algorithmic communities and substantive social/theoretical groups.
- Satyanarayan et al., Vega-Lite / declarative visualization grammar.
- Tamara Munzner, *Visualization Analysis and Design*.
- uncertainty-visualization and visual-inference literature should be used when adding confidence bands, uncertain classifications or probabilistic layouts.

The canonical cross-repository bibliography and interoperability architecture live in `TomiToivio/LaclauGPT#35`; Analysis-side DATS/DNA contracts are implemented under `TomiToivio/LaclauGPT-Data-Analysis#57`.
