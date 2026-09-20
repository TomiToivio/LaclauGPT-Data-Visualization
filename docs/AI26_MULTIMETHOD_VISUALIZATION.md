# AI26 multi-method visualization

This workspace consumes `laclaugpt.multimethod.v1` artifacts produced by `LaclauGPT-Data-Analysis`. Visualization does not fit MCA, detect DNA communities, infer frames, classify ideology, or rewrite the LaclauGPT paper.

## Phase 1 restoration decision

**Decision: adapt.** The existing multimethod renderer remains an isolated, read-only capability because its core assumptions still match the current Analysis/Visualization boundary: Analysis produces `laclaugpt.multimethod.v1` (with optional embedded `laclaugpt.social-space.v1`), and Visualization only filters/transforms those supplied products.

The Phase 1 adapter now validates the boundary before rendering. Every statement must have a unique `statement_id` and a non-empty canonical `source_url`; malformed embedded MCA payloads are rejected rather than guessed into shape. Deterministic chart-input snapshots keep rendering transforms reproducible and preserve source traceability.

This restoration does not alter Phase 0 list, inspect, export, review, or identity behavior. It introduces no storage dependency and remains removable by deleting the isolated multimethod page/view modules and their tests.

## Entry point

The unified Streamlit application exposes **AI26 Multimethod Explore** through its page navigation. The page searches the configured local Analysis directory and private `data/` tree for `laclaugpt.multimethod.v1` JSON artifacts. A researcher may also upload a JSON artifact for the current session.

Local CSV/JSONL/SQLite canonical records remain available independently. MongoDB, Redis, Neo4j and S3/Allas are not required to inspect a local artifact.

## Shared selection

The workspace applies one explicit statement selection for project artifacts using available upstream fields:

- time window;
- arena;
- platform;
- actor/organization;
- concept;
- review/validation status;
- minimum confidence;
- include/exclude abstained proposals.

A visible network edge threshold is available for readability. The UI reports the remaining edge count and does not silently apply an additional backbone algorithm.

## DNA

The DNA tab provides:

- signed actor–concept statement rows with evidence/source links;
- actor congruence;
- actor conflict;
- concept congruence;
- concept conflict;
- upstream community assignments;
- upstream temporal DNA windows.

Congruence and conflict remain separate. The dashboard does not calculate alternative projections or community assignments. Edge metadata is displayed as supplied by Analysis so method/parameter details remain inspectable when present.

## Framing

The framing tab treats frame elements as structured grounded objects. It provides:

- actor/concept/arena/platform × frame-component matrices;
- a heatmap of those descriptive counts;
- grounded frame-element rows;
- an ordered coded frame-structure co-occurrence table.

The co-occurrence display does not imply causal flow. Frame frequency is not interpreted as effectiveness or resonance.

## MCA / geometric data analysis

The MCA/GDA tab consumes `laclaugpt.social-space.v1` embedded in the multimethod artifact.

It provides:

- selectable factor plane dimensions;
- actor/document points;
- optional upstream cluster overlay;
- active modality table;
- supplementary modality table shown separately;
- modality contribution view for the selected axis;
- eigenvalues and inertia ratios;
- provenance showing active and supplementary variables.

Axes are never automatically named. Researchers should interpret dimensions from contribution, quality-of-representation and substantive evidence. Independently fitted period-specific MCA spaces are not animated as if their axes were directly comparable. Temporal MCA requires an upstream stable-reference, pooled, aligned or otherwise methodologically justified strategy.

## Cross-method comparison

For a selected actor the workspace places side by side:

- evidence-linked statements / DNA inputs;
- grounded frames;
- MCA coordinates;
- upstream DNA community proposal;
- upstream MCA cluster proposal;
- underlying evidence/source URLs.

Agreement between methods is not treated as automatic validation, and disagreement is not repaired into a master ideology score. Existing Laclau and sociotechnical-imaginary proposals remain optional record-level overlays in the ordinary dashboard/researcher-review views.

## Evidence and review

Every statement retains its canonical `source_url`, statement ID, source-record ID, stance, evidence span, confidence, validation status and abstention state when supplied upstream. The Evidence tab also reports which source URLs are present in the currently loaded canonical dashboard frame.

Human review continues to use the existing Researcher Review / review-store workflow. This workspace does not create a parallel review database.

## Methodological guardrails

The UI repeats these warnings visibly:

- frequency is not importance or hegemony;
- graph degree is not a nodal point;
- a network community is not an ideology;
- an opposition edge is not automatically an antagonistic political frontier;
- MCA proximity is relational statistical proximity in the constructed categorical space, not semantic/political identity or a social-network tie;
- MCA axes require researcher interpretation from contributing modalities and quality diagnostics;
- frame frequency is not frame effectiveness/resonance;
- LLM/model coding remains provisional until reviewed.

## Scalability

Visualization uses precomputed upstream DNA/MCA artifacts. Large-corpus controls are explicit filtering, precomputed temporal windows, and edge thresholds. Incremental AI26 Analysis runs can write new versioned JSON artifacts; the page discovers the newest local artifacts without changing the scientific source data.

## Public/private boundary

Tests use synthetic data only. Real AI26 artifacts, row-level data, review databases, operational settings and researcher notes belong under ignored `data/` or external private storage. No private AI26 rows are committed by this feature.
