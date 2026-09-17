export function semanticNebula(model) {
  const points = (model.semantic_points || []).map((point) => ({
    ...point,
    geometry: "analytical",
  }));
  return {
    points,
    geometry: points.length ? "analytical_projection" : "unavailable",
    note: points.length
      ? "Distances reflect the documented private-runtime projection."
      : "No semantic projection supplied; decorative orbital positions must not be read as semantic distance.",
  };
}

export function differenceNebula(model, countryA, countryB) {
  const totals = new Map();
  const byCountry = new Map();
  for (const edge of model.concept_edges || []) {
    const key = edge.canonical_term;
    totals.set(key, (totals.get(key) || 0) + Number(edge.weight || 0));
    const ckey = `${edge.country}\u001f${key}`;
    byCountry.set(ckey, (byCountry.get(ckey) || 0) + Number(edge.weight || 0));
  }
  const concepts = [...totals.keys()].sort();
  const aDen = concepts.reduce((sum, term) => sum + (byCountry.get(`${countryA}\u001f${term}`) || 0), 0) || 1;
  const bDen = concepts.reduce((sum, term) => sum + (byCountry.get(`${countryB}\u001f${term}`) || 0), 0) || 1;
  return concepts.map((term) => {
    const a = byCountry.get(`${countryA}\u001f${term}`) || 0;
    const b = byCountry.get(`${countryB}\u001f${term}`) || 0;
    return {
      canonical_term: term,
      country_a: countryA,
      country_b: countryB,
      count_a: a,
      count_b: b,
      share_a: a / aDen,
      share_b: b / bDen,
      descriptive_difference: a / aDen - b / bDen,
      statistic: "difference_in_within_country_share",
    };
  });
}
