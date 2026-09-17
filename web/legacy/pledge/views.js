export function discourseWeather(model, {normalized = false} = {}) {
  const groups = new Map();
  for (const row of model.records || []) {
    const date = row.date || "unknown";
    const country = row.country || "unknown";
    const key = `${date}\u001f${country}`;
    groups.set(key, (groups.get(key) || 0) + 1);
  }
  const totals = new Map();
  for (const [key, count] of groups) {
    const [date] = key.split("\u001f");
    totals.set(date, (totals.get(date) || 0) + count);
  }
  return [...groups].map(([key, count]) => {
    const [date, country] = key.split("\u001f");
    return {date, country, count, value: normalized ? count / totals.get(date) : count, normalized};
  });
}

export function topicLoom(model) {
  const recordById = new Map((model.records || []).map((row) => [row.source_id, row]));
  const counts = new Map();
  for (const token of model.tokens || []) {
    if (!["topics", "entities"].includes(token.field)) continue;
    const record = recordById.get(token.source_id);
    if (!record) continue;
    const left = `${record.country || "unknown"}:${token.field}`;
    const key = `${left}\u001f${token.canonical_term}`;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts].map(([key, weight]) => {
    const [source, target] = key.split("\u001f");
    return {source, target, weight, relation: "observed_cooccurrence"};
  });
}

export function grievanceAtlas(model) {
  const points = (model.semantic_points || []).map((point) => ({...point, geometry: "analytical"}));
  return {
    points,
    geometry: points.length ? "analytical_projection" : "unavailable",
    note: points.length
      ? "Distances come from the documented private-runtime projection."
      : "No semantic projection supplied; no spatial relationship is implied.",
  };
}
