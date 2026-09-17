# VASAMA visualization audit for issue #15

This audit covers only generic visualization/data-access mechanics useful to LaclauGPT. OSINT prompts, geopolitical categories, historical private data, credentials, session files and domain-specific assumptions are intentionally excluded.

## Historical coverage

The repository history exposed no March 2026 dashboard commit in the accessible default-branch history. The closest historical dashboard lineage is the September 2025 dashboard/geocoding series, while the explicitly requested `rag` branch remains available and was inspected directly. The `rag` tree contains private/session/runtime material; none of that content is copied here.

| VASAMA path | branch/commit | capability | decision | target visualization component | reason |
|---|---|---|---|---|---|
| `osint_dashboard.py` | `rag` (`94ec36d`) | single/multi-event Folium maps | adapt | canonical geomap | Useful multi-marker/drill-down pattern, but replace OSINT event schema and Folium-only assumptions with canonical location entities and Plotly/current plugin contract. |
| `osint_dashboard.py` | `rag` | date range + dataframe filtering | adapt | shared dashboard filters | Keep one filtered canonical frame feeding map/timeline/network rather than separate dashboard islands. |
| `osint_dashboard.py` | `rag` | selected-record table/details | adapt | Researcher Review linkage | Preserve source-record drill-down and human-readable summary linkage. |
| `osint_geocode.py` | `rag` | event location -> coordinates | reject runtime geocoding here; adapt provenance idea | geomap contract | Visualization must consume coordinates and their provenance, not call a geocoder or invent certainty. Historical code also contained a hard-coded Mapbox credential and `eval()` parsing, both explicitly rejected. |
| `osint_geocode.py` | `rag` | event timeline insertion | adapt | `timeline_events()` | Preserve extracted event date, label, source URL and evidence refs without Mongo-only side collections. |
| `osint_geocode.py` | `rag` | source/target network-edge insertion | adapt | `relations()` / `graph_projection()` | Generic edge mechanics are useful; LaclauGPT adds relation type, evidence, validation state, weight and canonical record provenance. |
| cron/dataframe scripts | `rag` | local periodically refreshed files | adapt | local profile | Current Visualization already loads local CSV/JSON/JSONL/SQLite without Mongo/Redis/S3/Neo4j. Cron/systemd may refresh those files externally. |
| `osint_dashboard.py` | `be034ab` and Sep 2025 dashboard lineage | Streamlit local dashboard | adapt | current Streamlit workbench | Reuse lightweight local-workbench concept, not OSINT fields or Mongo coupling. |
| removed historical graph code | `3b8d14d` | graph rendering experiment | reject implementation, retain requirement | canonical network view | Historical implementation was removed upstream; current LaclauGPT builds a bounded graph projection directly from canonical relations. |
| Mongo dashboard/map/timeline/network collections | Sep 2025 lineage | materialized visualization side tables | reject as requirement | canonical fallback + optional graph backend | Visualization should not require parallel Mongo collections. Canonical records remain sufficient in local mode; optional Graph/RAG backends can provide richer products. |

## Implemented canonical contracts

### Geomap

`research_views.map_points()` now:

- supports multiple locations per canonical record;
- reads locations/events already present in canonical/analysis data;
- never performs network geocoding;
- keeps `source_url`, summary, author, evidence refs and provenance;
- distinguishes `source-provided`, `geocoded`, `inferred`, `human-validated`, `human-reviewed-record` and `unrecorded` coordinate states;
- omits explicitly unresolved ambiguous locations even if candidate coordinates are present;
- preserves legacy `event_lat` / `event_lng` as a bounded fallback.

The existing shared sidebar filtering occurs before map/timeline/network view-model construction, so platform/country/language/formation/provenance filters automatically apply to all three. Dataset/arena/date/entity/signifier/frame filters can be added to the same shared filter layer as their canonical columns become consistently populated.

### Timeline

`timeline_events()` keeps source, collection, analysis and event clocks separate and now carries record summaries, review state and event evidence refs. `discourse_timeline()` provides a source-linked long form for actor, entity, signifier, topic and formation appearances over source time. These are descriptive observations, not claims that frequency equals ideological importance.

### Social/discourse network

`transforms.relations()` and `graph_projection()` now provide a canonical/no-Neo4j fallback with:

- source -> target relation type;
- source record/document identifiers;
- evidence references;
- extracted/inferred/human-validated state;
- edge weights and duplicate aggregation;
- contributing source URLs;
- node labels and best-effort node kinds;
- a hard `max_edges` bound to prevent browser-size explosions.

This fallback is rebuildable from canonical records. When issue #14 supplies an optional Graph/RAG backend, its graph product should feed the same researcher-facing network contract rather than replace canonical storage.

## Shared Graph/RAG UI boundary

Issue #15 and issue #14 share these contracts:

- shared filtered canonical frame;
- stable `source_url` links back to Researcher Review;
- source/evidence provenance on locations, events and edges;
- validation/origin state rather than treating inferred relations as fact;
- bounded graph products;
- local canonical fallback when Neo4j/RAG is disabled.

Graph Explorer, Context Explorer and Research Q&A belong to issue #14 because they require retrieval/backend behavior. Map, timeline and canonical graph projection remain usable without Neo4j.

## Local single-machine profile

The default local path remains deliberately boring and reliable:

```text
Collection / Analysis
    -> canonical CSV / JSON / JSONL / SQLite / files
    -> LaclauGPT Data Visualization
       -> map
       -> timeline
       -> network projection
       -> Researcher Review
```

MongoDB, Redis, S3/Allas and Neo4j are optional. External cron/systemd may refresh local files, but the dashboard itself does not need a scheduler.

## Security conclusions

Do not copy from historical VASAMA:

- Telegram/session/auth files;
- hard-coded geocoding keys or credentials;
- private corpora/dataframes/reports;
- endpoints or local paths;
- `eval()` parsing of persisted data;
- geopolitical/OSINT prompts or categories;
- Mongo-only visualization schemas.

The useful inheritance is architectural: shared filtering, source-linked map/timeline/network exploration, local refreshability and drill-down. The scientific data contract remains LaclauGPT's canonical schema.
