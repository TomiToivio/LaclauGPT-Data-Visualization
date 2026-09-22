# AI26 Visualization configuration

AI26 Visualization is a downstream presentation/control profile over the canonical AI26 research contracts. It must not become a second scientific codebook.

## Ownership

- `TomiToivio/LaclauGPT` owns the project theory, canonical contracts and reference documentation.
- `TomiToivio/LaclauGPT-Data-Analysis` owns analytical semantics, the public AI26 codebook and result schemas.
- `TomiToivio/LaclauGPT-Data-Collection` owns source collection configuration and sampling provenance.
- `LaclauGPT-Data-Visualization` owns presentation defaults, enabled dashboard views, filters, safe limits, capability flags and semantic warnings.

The public dashboard profile is `configs/projects/ai26.yaml`. Its `canonical_analysis_codebook` points to the current public Analysis codebook instead of duplicating it.

## Phase 1 capability parity

Visualization mirrors the Analysis-owned Phase 1 capability switches under the same `analysis` namespace. These settings are downstream gates only; Visualization never turns on an upstream analytical stage.

The current Phase 1 defaults are:

```yaml
analysis:
  sna: false
  dna_statement_coding:
    enabled: false
  critical_ai:
    enabled: false
  rdf:
    enabled: false
    required: false
    graphrag:
      enabled: false
```

Critical AI, DNA and SNA are therefore off by default. RDF is also optional and disabled by default. The ordinary dashboard and canonical graph projection remain usable without RDF.

`optional_capabilities` remains a presentation-facing capability summary. Its Phase 1 values must agree with the nested `analysis` policy for `sna`, `dna`, `critical_ai`, `rdf` and `rdf_graphrag`.

## Canonical AI26 IDs

Visualization preserves the six current public formation IDs exactly:

- `accelerationism`
- `doomerism`
- `left-wing accelerationism`
- `ai safety`
- `ai critical`
- `anti-ai`

They are provisional, multi-label aggregation anchors. Source inclusion, actor identity, chart prominence and network position are not formation membership.

## Composition

The supported order is:

```text
public Visualization AI26 profile
  + authorized private AI26 visualization overlay
  + optional machine-specific private overlay
  + protected environment/secrets handled by runtime Settings
  = effective dashboard configuration
```

`compose_ai26_profile()` performs the file-layer composition. Lists and scalars are explicitly replaced by the later layer; mappings merge recursively. An overlay may change presentation/runtime defaults but may never change the canonical `project_id=ai26`.

A production caller may pass `require_private=True`. In that mode missing private configuration fails closed instead of silently falling back to a public demo profile.

The existing `Settings` class remains authoritative for secret-bearing runtime values such as MongoDB/Redis/S3 credentials. These are not stored in this profile.

## Private deployment paths

On an authorized research host, checkout locations are deployment-specific and must come from private runtime configuration. Public documentation must use placeholders or environment variables rather than real host paths.

Private Visualization configuration should live under the protected private configuration tree's `visualization/ai26/` area. Runtime logs, caches, exports and notes stay outside the public repository and should be kept under the private/runtime tree or another protected path defined by private configuration.

Do not copy private source lists, researcher notes, credentials or operational endpoint values into the public Visualization repository.

## Presentation codebook rule

Visualization-specific mapping may add display labels, descriptions, aliases, filter groupings and warnings. It may not:

- assign actors permanently to formations;
- invent new scientific classifications to make a chart easier to draw;
- replace the Analysis codebook;
- infer hegemony, nodal status, antagonism or equivalence from chart/network metrics.

If the upstream public codebook changes IDs, update this profile deliberately and add/adjust tests. Do not silently rename upstream IDs in the dashboard.

## Required safeguards

Relevant views should surface the public profile's safeguards, including:

- frequency is not hegemony;
- degree/centrality is not nodal status;
- network community is not ideological formation;
- DNA agreement is not Laclaudian equivalence;
- conflict edges are not automatically antagonistic frontiers;
- semantic proximity is not equivalence;
- sentiment is not affective investment;
- topic prevalence is not discourse or hegemony;
- source-family prior is not current-document ideology.

## RDF policy

RDF uses the single documented policy shape consumed directly by `RDFProjectPolicy.from_mapping()`:

```yaml
analysis:
  rdf:
    enabled: false
    required: false
    graphrag:
      enabled: false
```

Do not use flat `rdf` or `rdf_graphrag` flags as the authoritative RDF policy. Runtime service configuration may provide an RDF endpoint, but it cannot override project policy and enable RDF.

When RDF is disabled, the RDF explorer reports that it is disabled and stops cleanly. The ordinary dashboard, including canonical MongoDB/CSV graph projections, remains independent from RDF.

Synthetic tests may enable RDF explicitly to verify the optional path without making RDF a Phase 1 requirement.

## Diagnostics and provenance

`AI26DashboardProfile.safe_summary()` is the supported project-profile diagnostic representation. `Settings.safe_summary()` remains the runtime diagnostic representation. Secret-bearing runtime values must never be copied into the project profile.

Profile revisions are calculated only from the sanitized presentation configuration. Do not hash raw secret-bearing environment mappings for dashboard-visible provenance.

## Private overlay example

A private overlay can safely contain non-secret presentation overrides such as:

```yaml
project_id: ai26
limits:
  refresh_seconds: 15
analysis:
  rdf:
    enabled: true
    required: false
    graphrag:
      enabled: false
optional_capabilities:
  rdf: true
  rdf_graphrag: false
private_overlay_required: true
```

Private source/account aliases or non-public researcher navigation metadata may also live there when authorized. Credentials remain in protected environment files and must not be committed merely because the repository is private.

## Public-tree verification

Before merging public changes run:

```bash
python scripts/check_public_tree.py
ruff check .
pytest
```

Public tests use synthetic/public-safe data only.

## Relationship to the research-server deployment

Issue #35 consumes this configuration during research-server installation. Deployment should compose the public profile with the authorized private overlay and then load distributed runtime secrets from the protected environment. Visualization must use the same canonical `ai26` MongoDB/Redis/Allas namespace as Collection and Analysis.
