# Hermes operation

Hermes operates `LaclauGPT-Data-Visualization` as a downstream visualization agent. It must not collect data, run analysis inference, reinterpret canonical identity, or bypass researcher review semantics.

Use the functions in `laclaugpt_visualization.integrations.hermes`. They call the same canonical loaders and configuration used by human operation.

## Safe operations

- `inspect_effective_config(settings)` returns only non-secret effective configuration.
- `validate_analysis_input(source, settings)` reconstructs canonical records before checking `source_url` identity and schema versions.
- `inspect_dataset(source, settings)` returns bounded metadata rather than raw research rows.
- `validate_service(settings)` performs an offline readiness check and returns the canonical Streamlit launch command without starting infrastructure.
- `export_summary(...)` writes an auditable metadata export under the configured private `data/exports/` tree.
- `request_human_review(source_url, ...)` appends an agent audit record using canonical `source_url` identity.
- `clear_derived_cache(settings)` may clear local derived cache, but deliberately refuses to flush shared Redis implicitly.

Agent actions use caller `hermes-agent` and execution `agent` where audit records are written.

## Boundaries

Real datasets, review records, credentials, Redis/MongoDB/S3 endpoints, browser/session material, TLS keys, domains, CSC project identifiers, and machine-specific deployment values remain outside Git. Distributed Redis is coordination/settings/cache, MongoDB is the queryable record plane, and S3/CSC Allas is the large-object plane.
