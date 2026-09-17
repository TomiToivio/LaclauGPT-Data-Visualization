import test from "node:test";
import assert from "node:assert/strict";

import {
  SCIENTIFIC_SAFEGUARDS,
  cytoscapeElements,
  evidenceForSelection,
  graphologyData,
  semanticMetadata,
} from "./semantic-renderers.js";

const view = {
  projection_id: "p1",
  graph_type: "actor_concept_bipartite",
  node_semantics: "actors and concepts",
  edge_semantics: "coded statements",
  projection_method: "statement affiliation",
  weighting_method: "statement count",
  temporal_scope: { start: "2026-09-01", end: "2026-09-17" },
  filters: { language: "fi" },
  producer: { id: "laclaugpt-data-analysis", version: "0.2" },
  provenance_id: "prov-1",
  nodes: [
    {
      id: "a1",
      label: "Tutkija Ω",
      node_type: "actor",
      review_status: "ACCEPTED",
      evidence: [{ source_url: "https://example.org/a", statement_id: "s1" }],
      external_ids: { dna: "actor-7" },
    },
    { id: "c1", label: "demokratia", node_type: "concept" },
  ],
  edges: [
    {
      id: "s1",
      source: "a1",
      target: "c1",
      edge_type: "statement",
      weight: 1,
      review_status: "PROVISIONAL",
      uncertainty: "low",
      evidence: [{ source_url: "https://example.org/a", evidence_id: "ev1" }],
    },
  ],
};

test("Cytoscape adapter preserves semantic and evidence fields without layout", () => {
  const payload = cytoscapeElements(view);
  assert.equal(payload.nodes[0].data.label, "Tutkija Ω");
  assert.equal(payload.nodes[0].data.external_ids.dna, "actor-7");
  assert.equal(payload.edges[0].data.uncertainty, "low");
  assert.equal(payload.nodes[0].position, undefined);
});

test("Graphology adapter is renderer-thin and keeps semantics", () => {
  const payload = graphologyData(view);
  assert.equal(payload.nodes[0].attributes.node_type, "actor");
  assert.equal(payload.edges[0].attributes.edge_type, "statement");
  assert.equal(payload.nodes[0].attributes.x, undefined);
});

test("semantic metadata and drill-down remain explicit", () => {
  const metadata = semanticMetadata(view);
  assert.equal(metadata.projection_method, "statement affiliation");
  assert.equal(metadata.filters.language, "fi");
  assert.ok(metadata.safeguards.includes("community/cluster != ideological formation"));
  assert.equal(evidenceForSelection(view, "s1")[0].evidence_id, "ev1");
  assert.ok(SCIENTIFIC_SAFEGUARDS.length >= 8);
});
