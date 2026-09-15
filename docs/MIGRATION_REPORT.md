# Visualization migration report

Issue #2 consolidates three historical visualization lines into this repository without copying private data/configuration or preserving monolithic dashboard architecture.

## Public `LaclauGPT-Discourse-Analysis/laclaugpt/visualization/`

| Historical file | Classification | Treatment |
| --- | --- | --- |
| `__init__.py` | REIMPLEMENT_CLEANLY | Public API kept small in this package. |
| `app.py` | REIMPLEMENT_CLEANLY | Useful filters/document views/caveats generalized into unified app + pure transforms. |
| `dashboard.py` | REIMPLEMENT_CLEANLY | Researcher document/review concepts retained, monolithic Streamlit implementation rejected. |
| `data.py` | MIGRATE | Canonical loading/filtering concepts re-homed in `data.py` + `canonical.py`. |
| `graph.py` | REIMPLEMENT_CLEANLY | Graph projection inputs represented by pure transforms; UI layout is descriptive only. |
| `launcher.py` | ALREADY_IMPLEMENTED | Destination CLI/runtime already owns launch behavior. |
| `live.py` | MIGRATE | Corpus status, actor/signifier/timeline/relation summaries generalized into `transforms.py`. |
| `live_dashboard.py` | REIMPLEMENT_CLEANLY | Monitor concepts folded into unified Monitor mode rather than copied. |
| `review.py` | MIGRATE | Typed review semantics re-homed under `review/`; persistence is independent of UI. |
| `runtime.py` | ALREADY_IMPLEMENTED | Destination config/runtime/profiles are canonical. |
| `unified_dashboard.py` | REIMPLEMENT_CLEANLY | The one-application principle is implemented directly in `app.py` with three modes. |

No historical module remains a runtime dependency.

## AI26 private live dashboard

Audited as a feature/reference source only. Reusable concepts retained:

- polling/file-oriented canonical JSONL/NDJSON input;
- analyzed vs awaiting-analysis status;
- latest source/analysis timestamps;
- formations, signifiers, actors and relation views;
- project-neutral filters and near-real-time local operation;
- review integration concepts;
- explicit warning that counts, confidence, degree and layout do not establish theoretical validity.

`PRIVATE_DO_NOT_COPY`: project-specific configuration, target lists, runtime paths, private data, operational credentials and any AI26 row-level content.

## Legacy EP24 researcher dashboard

Audited as a workflow source. Reusable concepts retained:

- record/video selection and close reading;
- human-readable summary;
- transcript, translation, OCR and multimodal/frame output;
- entities/persons, topics/themes, sentiment and discourse/populism fields;
- researcher notes and checked/dubious/exclusion concepts;
- rerun analysis/ASR/OCR and media reprocess/split/cut request concepts;
- country/platform/date-oriented exploration;
- researcher corrections and exports as downstream concepts.

`LEGACY_ADAPTER`: useful historical columns are mapped only in `legacy_ep24.py`.

`OBSOLETE`: global mutable dataframe state, giant column-config tables, ad-hoc JSON notes, direct analysis logic in UI, hard-coded databases and authentication/configuration embedded in the dashboard.

`PRIVATE_DO_NOT_COPY`: the historical dashboard contained credential-bearing MongoDB configuration and operational host information. None of those values are copied into this repository, documentation, tests or examples.

## Destination architecture

The consolidated flow is:

```text
canonical/legacy adapter
        ↓
data loaders + normalization + filters
        ↓
pure monitor/explore transforms
        ↓
Monitor | Researcher Review | Explore
        ↓
typed review store (SQLite default, Mongo optional)
```

The canonical nested record is primary. EP24 compatibility is bounded. Visualization never reimplements Collection or Analysis.
