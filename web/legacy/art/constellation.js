export function buildConstellation(model, { family = null } = {}) {
  const edges = (model.concept_edges || []).filter((edge) => !family || edge.concept_family === family);
  const countries = [...new Set(edges.map((edge) => edge.country))].sort();
  const concepts = [...new Set(edges.map((edge) => edge.canonical_term))].sort();
  return {
    nodes: [
      ...countries.map((id) => ({ id: `country:${id}`, label: id, kind: "country" })),
      ...concepts.map((id) => ({ id: `concept:${id}`, label: id, kind: "concept" })),
    ],
    links: edges.map((edge) => ({
      source: `country:${edge.country}`,
      target: `concept:${edge.canonical_term}`,
      weight: Number(edge.weight || 0),
      family: edge.concept_family,
    })),
  };
}

export function createArtDashboard(root, model, options = {}) {
  const reducedMotion = options.reducedMotion ?? window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  let researchMode = options.researchMode ?? true;
  let paused = reducedMotion;
  root.innerHTML = "";

  const controls = document.createElement("div");
  const toggle = document.createElement("button");
  const pause = document.createElement("button");
  const legend = document.createElement("p");
  const canvas = document.createElement("canvas");
  canvas.width = 960; canvas.height = 540; canvas.tabIndex = 0;
  canvas.setAttribute("aria-label", "Country and concept constellation");

  function draw() {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const graph = buildConstellation(model);
    const countries = graph.nodes.filter((node) => node.kind === "country");
    const concepts = graph.nodes.filter((node) => node.kind === "concept");
    const positions = new Map();
    countries.forEach((node, i) => positions.set(node.id, { x: 160, y: 80 + i * 80 }));
    concepts.forEach((node, i) => positions.set(node.id, { x: 620, y: 50 + (i * 47) % 440 }));
    ctx.font = researchMode ? "14px sans-serif" : "15px monospace";
    for (const link of graph.links) {
      const a = positions.get(link.source), b = positions.get(link.target);
      if (!a || !b) continue;
      ctx.globalAlpha = Math.min(0.9, 0.15 + link.weight * 0.12);
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    for (const node of graph.nodes) {
      const p = positions.get(node.id); if (!p) continue;
      ctx.beginPath(); ctx.arc(p.x, p.y, node.kind === "country" ? 7 : 4, 0, Math.PI * 2); ctx.fill();
      ctx.fillText(node.label, p.x + 10, p.y + 4);
    }
    legend.textContent = researchMode
      ? "Research mode: exact edge weights come from parsed source mentions. Layout is decorative, not semantic distance."
      : "Exhibition mode: animated/orbital presentation may be decorative. Only documented weights encode evidence.";
    toggle.textContent = researchMode ? "Switch to exhibition mode" : "Switch to research mode";
    pause.textContent = paused ? "Resume animation" : "Pause animation";
  }
  toggle.addEventListener("click", () => { researchMode = !researchMode; draw(); });
  pause.addEventListener("click", () => { paused = !paused; draw(); });
  controls.append(toggle, pause);
  root.append(controls, legend, canvas);
  draw();
  return { draw, isResearchMode: () => researchMode, isPaused: () => paused };
}
