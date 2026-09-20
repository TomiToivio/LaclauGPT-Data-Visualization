# Phase 1 specialized dashboard restoration

Issue #96 establishes the one-dashboard-at-a-time restoration pattern with the **Pledge Dashboard** only.

The dashboard is disabled by default and enabled with:

```bash
LACLAUGPT_VIS_SPECIALIZED_PLEDGE_DASHBOARD_ENABLED=true
```

It renders from the same canonical dataframe projection used by the common workbench. It does not add a second loader or storage architecture, does not change Phase 0 behavior, and preserves `source_url` as record identity. Political alignment is shown only when it is source-observed or explicitly marked as a historical `legacy_derived_alignment`; missing values remain missing.

The plugin registry now marks `pledge_dashboard` as implemented. The Streamlit tab is added only when the feature flag is enabled, so rollback is a single configuration change.

Other specialized dashboards, including the Art dashboard, remain untouched and must be restored in separate issues.
