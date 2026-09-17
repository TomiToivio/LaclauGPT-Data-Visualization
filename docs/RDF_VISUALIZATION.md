# Optional RDF / Linked Data visualization

RDF is an optional research lens over the same canonical evidence used by the normal LaclauGPT dashboard. It does **not** replace MongoDB, CSV, canonical graph products, researcher review state, or the existing evidence model.

## Project policy is authoritative

The visualization layer reads project configuration conceptually as:

```yaml
analysis:
  rdf:
    enabled: false
    required: false
    graphrag:
      enabled: false
```

Omitting `analysis.rdf` is equivalent to disabled. Runtime configuration may supply an RDF service location, but it cannot turn RDF on when project policy disables it.

The dashboard looks for project YAML under `data/config/<project_id>.yaml|yml` and then `data/config/project.yaml|yml`. An enabled project may configure the private runtime variable `LACLAUGPT_VIS_RDF_SERVICE_URL` to point to the Analysis-owned RDF service. The endpoint must not be committed.

When RDF is disabled, the RDF page clearly reports that project policy disables it. When RDF is enabled but no service is configured or reachable, the RDF page degrades gracefully and the ordinary CSV/MongoDB dashboard remains fully usable.

## Vendor-neutral provider contract

`laclaugpt_visualization.rdf.RDFQueryProvider` defines the visualization contract:

- `health()` / `capabilities()`
- `query_subgraph(filters, limits)`
- `query_table(query, limit, timeout_seconds)`
- `describe_resource(uri)`
- `list_named_graphs()`
- `export(format, selection, limits)`
- `graphrag_context(selection)`

`AnalysisHTTPRDFProvider` is an adapter for an Analysis-owned HTTP API. UI code therefore does not depend directly on Fuseki, GraphDB, Stardog, Blazegraph, Virtuoso, Oxigraph, RDFLib, or another RDF implementation.

## Bounded graph explorer

The Streamlit page `pages/rdf_explorer.py` supports bounded semantic exploration with:

- class/type and predicate filters;
- named/project graph filters;
- source, author, time, formation, signifier, entity, review-state and confidence filters;
- resource search/describe;
- neighbor depth plus strict node/edge limits;
- graph/table switching;
- compact prefixes and multilingual labels while retaining exact URIs;
- evidence/provenance drill-down;
- query/provenance display when the provider returns it.

The visualization refuses provider payloads that exceed requested node or edge bounds. Layout geometry is descriptive only and is not interpreted as theoretical distance.

## Theory-aware semantics

The RDF helper recognizes readable labels for the minimal LaclauGPT vocabulary where present, including articulation, discourse formation, signifier, empty/floating signifier candidates, nodal-point candidates, chains of equivalence, antagonism, and discursive frontiers.

The UI repeats the same safeguards as the rest of the dashboard: graph degree or centrality is not a nodal point; prominence is not hegemony; communities are not automatically ideological formations; co-occurrence is not equivalence; negative edges do not automatically establish an antagonistic frontier; layout distance is not theoretical distance.

Standard vocabularies are compacted for display, including RDF/RDFS/OWL, PROV-O, DCTERMS/DCAT, Schema.org, Web Annotation, SKOS, OntoLex, NIF, OWL-Time, GeoSPARQL and AIF. Exact URIs remain available for reproducibility.

## Safe query UX

Advanced SPARQL is read-only. The dashboard accepts SELECT, CONSTRUCT, DESCRIBE and ASK while rejecting update/federation operations such as INSERT, DELETE, LOAD, CLEAR, CREATE, DROP, COPY, MOVE, ADD and SERVICE. Queries carry explicit result and timeout limits.

The Analysis service remains responsible for final enforcement and authorization.

## Evidence and provenance

`evidence_path()` normalizes existing identifiers into the drill-down path:

```text
RDF node/edge
 -> analytical object
 -> evidence annotation/span/frame/transcript
 -> canonical source record
 -> analysis run/model/plugin/prompt/codebook
 -> human review status
```

This is a view over existing evidence/review identifiers, not a new review database.

## RDF export

The RDF page requests bounded exports from the Analysis service instead of materializing RDF in Streamlit. Supported request formats are JSON-LD, Turtle, N-Quads, N-Triples and optional TriG/RDF/XML when the backend advertises support.

## GraphRAG

RDF GraphRAG UI is separately gated by `analysis.rdf.graphrag.enabled`. When disabled, ordinary RDF browsing, query and export remain available. When enabled, the page can request an inspectable context bundle containing graph paths/nodes, evidence references and retrieval metadata from the Analysis provider.

## Tests

`tests/test_issue31_rdf_visualization.py` is offline and synthetic. It covers disabled/enabled policy, GraphRAG gating, missing-provider status metadata, strict graph limits, read-only SPARQL validation, URI/prefix and multilingual label rendering, standard/LaclauGPT semantics, evidence/provenance identifiers, and vendor-neutral plugin metadata.
