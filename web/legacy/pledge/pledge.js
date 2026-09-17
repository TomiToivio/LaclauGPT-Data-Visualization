export function filterRecords(model, state = {}) {
  const mode = state.provenanceMode || "observed";
  return (model.records || []).filter((row) => {
    if (mode === "observed" && row.alignment_observation_status !== "observed") return false;
    if (mode === "missing" && row.alignment_observation_status !== "missing") return false;
    if (state.country && row.country !== state.country) return false;
    if (state.platform && row.platform !== state.platform) return false;
    return true;
  });
}

export function aggregateTemporal(records) {
  const counts = new Map();
  for (const row of records) {
    const key = `${row.date || "unknown"}\u001f${row.country || "unknown"}`;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()].map(([key, count]) => {
    const [date, country] = key.split("\u001f");
    return { date, country, count };
  }).sort((a, b) => a.date.localeCompare(b.date) || a.country.localeCompare(b.country));
}

export function createPledgeDashboard(root, model, options = {}) {
  const state = { provenanceMode: options.provenanceMode || "observed" };
  root.innerHTML = "";
  const controls = document.createElement("div");
  const select = document.createElement("select");
  for (const [value, label] of [["observed", "Observed only"], ["all", "Observed + legacy-derived"], ["missing", "Missingness view"]]) {
    const option = document.createElement("option"); option.value = value; option.textContent = label; select.appendChild(option);
  }
  select.value = state.provenanceMode;
  const status = document.createElement("p");
  const ledger = document.createElement("table");
  ledger.setAttribute("aria-label", "Pledge research ledger");
  function render() {
    state.provenanceMode = select.value;
    const rows = filterRecords(model, state);
    status.textContent = `${rows.length} records. Alignment provenance mode: ${state.provenanceMode}.`;
    ledger.innerHTML = "<thead><tr><th>Date</th><th>Country</th><th>Platform</th><th>Grievance</th><th>Alignment</th><th>Provenance</th></tr></thead>";
    const body = document.createElement("tbody");
    for (const row of rows) {
      const tr = document.createElement("tr");
      for (const value of [row.date, row.country, row.platform, row.grievance, row.political_alignment, row.alignment_observation_status]) {
        const td = document.createElement("td"); td.textContent = value ?? ""; tr.appendChild(td);
      }
      body.appendChild(tr);
    }
    ledger.appendChild(body);
  }
  select.addEventListener("change", render);
  controls.append("Provenance lens: ", select);
  root.append(controls, status, ledger);
  render();
  return { state, render, temporal: () => aggregateTemporal(filterRecords(model, state)) };
}
