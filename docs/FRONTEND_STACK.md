# Frontend stack decision for the plugin workbench

Issue #26 expands this repository from a mostly read-only dashboard into a researcher workbench with configuration, editing, notes, queues and agent/RAG interaction. That increases frontend-state complexity, but it does **not** justify an immediate rewrite.

## Recommendation

Keep **Streamlit** for the current implementation while making plugin/service contracts portable. Re-evaluate only after the state-changing plugins are exercised with real distributed deployments.

The architecture should make a future React/Dash frontend a renderer swap rather than a data/service rewrite.

## Libraries to use now

### Plotly

Keep Plotly for ordinary distributions, timelines, scatter/embedding plots and lightweight maps. It is already a project dependency and is adequate for most descriptive research views.

### Streamlit built-ins

Use native `st.dataframe`, `st.data_editor`, forms, dialogs/fragments and chat primitives for components that do not need a bespoke browser renderer. Prefer simple native controls for settings rather than exposing raw YAML/JSON by default.

### Streamlit Custom Components v2

For richer components, prefer the current Components v2 API rather than old one-off wrappers. It provides a practical bridge to TypeScript/React components while retaining the Python workbench.

Good candidates:

- interactive graph canvas;
- richer map layers;
- specialized annotation/media widgets;
- a structured ethnography editor if Markdown/text areas become limiting.

## JavaScript candidates

| Need | Candidate | Why / when |
| --- | --- | --- |
| semantically rich discourse graphs | Cytoscape.js | strong node/edge styling, selection, compound graph concepts and graph interaction |
| very large networks | Sigma.js + Graphology | WebGL-oriented rendering and graph data structures when Cytoscape/Plotly becomes slow |
| richer maps | MapLibre GL JS | modern open map rendering without binding the backend to a GIS stack |
| very large geospatial layers | deck.gl | scalable GPU layers on top of map views when event volume requires it |
| large editable research tables | AG Grid / maintained Streamlit wrapper | only if native dataframe/editor features or performance are insufficient |
| declarative statistical plots | Vega-Lite / Altair | concise grammar for some research graphics; optional rather than mandatory |
| rich research/ethnography notes | TipTap | maintained structured editor if Markdown is insufficient |
| raw structured configuration | Monaco Editor | only for advanced JSON/YAML users; ordinary settings should be generated forms |

For critical components, prefer a small in-repository Components v2 bridge around a stable JS library over an abandoned Streamlit wrapper.

## Alternatives to Streamlit

| Criterion | Streamlit | Plotly Dash | FastAPI + React/TypeScript | Panel / NiceGUI |
| --- | --- | --- | --- | --- |
| Python/dataframe integration | excellent | excellent | API boundary required | strong |
| migration cost | lowest | medium | highest | medium |
| plugin/component freedom | good with Components v2 | good, React-based component ecosystem | excellent | good |
| complex client state | acceptable, rerun model can become awkward | better explicit callback model | excellent | generally better than simple Streamlit flows |
| websocket/live queue UX | possible but not its strongest model | possible | excellent | possible |
| large editable tables | native moderate; AG Grid optional | strong via components | excellent | varies |
| graph/map JS integration | via custom component | via components, including Cytoscape ecosystem | direct | via extensions/components |
| auth/authorization architecture | deployment/service layer required | deployment/service layer required | most explicit/control-friendly | deployment/service layer required |
| automated frontend testing | moderate | good | excellent | moderate |
| current code reuse | excellent | moderate | backend transforms/services reusable | moderate |

## Migration trigger

Do not migrate because another framework is more fashionable. Reconsider Streamlit when several of these become persistent problems in real use:

- queue/chat updates need continuous bidirectional state that fights Streamlit reruns;
- large record editors require complex optimistic state and conflict resolution;
- multi-pane graph/map/table selection needs substantial browser-local coordination;
- authentication/authorization needs a richer application shell;
- custom components dominate the UI to the point that Streamlit is merely an iframe orchestrator;
- frontend regression testing becomes a major requirement.

If those triggers occur, the preferred long-term architecture is **FastAPI (or equivalent Python API) + React/TypeScript**. It gives direct access to Cytoscape/Sigma, MapLibre/deck.gl, AG Grid, TipTap, TanStack-style query/state tooling and websocket streams while preserving Python analytical/service code behind APIs.

**Plotly Dash** is the strongest Python-first middle path if explicit callback/state structure is the main problem but a separate TypeScript application is not yet warranted.

Panel and NiceGUI remain reasonable experiments, but migration should require a demonstrated advantage on LaclauGPT workloads, not a synthetic demo.

## Data/UI separation that makes migration cheap

Regardless of framework:

- providers expose logical `DataProduct` capabilities;
- plugin specs declare product/backend/permission requirements;
- transforms do not depend on Streamlit;
- MongoDB/Redis/notes access goes through injected service adapters;
- task execution remains in Collection/Analysis workers, never inside the browser/UI process;
- evidence/provenance links are first-class;
- UI mutation permissions are enforced at the service/action boundary, not merely by hiding buttons.

That separation is the important investment. The frontend framework can then evolve without rewriting the research pipeline.
