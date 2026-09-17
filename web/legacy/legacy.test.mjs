import test from "node:test";
import assert from "node:assert/strict";
import { filterRecords, aggregateTemporal } from "./pledge/pledge.js";
import { buildConstellation } from "./art/constellation.js";

test("pledge provenance lens excludes derived rows by default", () => {
  const model = {records:[
    {date:"2024-01-01",country:"FI",alignment_observation_status:"observed"},
    {date:"2024-01-01",country:"PL",alignment_observation_status:"legacy_derived"},
  ]};
  const rows = filterRecords(model, {});
  assert.equal(rows.length, 1);
  assert.equal(aggregateTemporal(rows)[0].count, 1);
});

test("art constellation maps documented weights without inventing geometry", () => {
  const graph = buildConstellation({concept_edges:[
    {country:"FI",canonical_term:"public ai",concept_family:"themes",weight:2},
  ]});
  assert.equal(graph.nodes.length, 2);
  assert.equal(graph.links[0].weight, 2);
});
