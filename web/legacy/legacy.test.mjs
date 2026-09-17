import test from "node:test";
import assert from "node:assert/strict";
import { filterRecords, aggregateTemporal } from "./pledge/pledge.js";
import { discourseWeather, topicLoom, grievanceAtlas } from "./pledge/views.js";
import { buildConstellation } from "./art/constellation.js";
import { semanticNebula, differenceNebula } from "./art/semantic.js";

test("pledge provenance lens excludes derived rows by default", () => {
  const model = {records:[
    {source_id:"1",date:"2024-01-01",country:"FI",alignment_observation_status:"observed"},
    {source_id:"2",date:"2024-01-01",country:"PL",alignment_observation_status:"legacy_derived"},
  ]};
  const rows = filterRecords(model, {});
  assert.equal(rows.length, 1);
  assert.equal(aggregateTemporal(rows)[0].count, 1);
});

test("pledge weather normalizes within date and loom uses observed co-occurrence", () => {
  const model = {
    records:[
      {source_id:"1",date:"2024-01-01",country:"FI"},
      {source_id:"2",date:"2024-01-01",country:"PL"},
    ],
    tokens:[{source_id:"1",field:"topics",canonical_term:"ai"}],
  };
  const weather = discourseWeather(model, {normalized:true});
  assert.equal(weather.reduce((sum, row) => sum + row.value, 0), 1);
  assert.deepEqual(topicLoom(model)[0], {
    source:"FI:topics", target:"ai", weight:1, relation:"observed_cooccurrence",
  });
  assert.equal(grievanceAtlas(model).geometry, "unavailable");
});

test("art constellation maps documented weights without inventing geometry", () => {
  const graph = buildConstellation({concept_edges:[
    {country:"FI",canonical_term:"public ai",concept_family:"themes",weight:2},
  ]});
  assert.equal(graph.nodes.length, 2);
  assert.equal(graph.links[0].weight, 2);
});

test("art semantic views distinguish analytical coordinates and descriptive differences", () => {
  assert.equal(semanticNebula({}).geometry, "unavailable");
  const rows = differenceNebula({concept_edges:[
    {country:"FI",canonical_term:"public ai",weight:2},
    {country:"PL",canonical_term:"public ai",weight:1},
    {country:"PL",canonical_term:"sovereignty",weight:1},
  ]}, "FI", "PL");
  const publicAi = rows.find((row) => row.canonical_term === "public ai");
  assert.equal(publicAi.statistic, "difference_in_within_country_share");
  assert.equal(publicAi.descriptive_difference, 0.5);
});
