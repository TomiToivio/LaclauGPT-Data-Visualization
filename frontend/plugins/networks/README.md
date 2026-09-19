# Phase-1 optional network prototypes

These prototypes are intentionally isolated from the Phase-0 Streamlit/Plotly runtime. They use browser ESM/CDN imports so **no npm dependency or default dashboard behavior changes**.

## Choose Cytoscape vs Sigma

- **Cytoscape.js**: default candidate for small/medium research graphs where interaction, rich styling, graph manipulation and evidence drill-down matter most.
- **Sigma.js + Graphology**: candidate for much larger graphs where WebGL rendering and a dedicated graph data model matter more than rich per-element UI.
- **D3**: retain for bespoke encodings, not as a reason to rebuild commodity graph interaction from primitives.

The Cytoscape prototype is a tiny actor-concept view. The Sigma prototype deliberately creates a larger synthetic graph to exercise the scale-oriented path.

All graph prominence is descriptive. Degree is not a nodal point, layout proximity is not equivalence, a cluster is not an ideology, and frequency is not hegemony.

Activation is deferred until Phase 1.
