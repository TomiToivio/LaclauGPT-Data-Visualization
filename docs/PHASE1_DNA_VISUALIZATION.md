# Phase 1 DNA visualization decision

Issue #94 restores Discourse Network Analysis visualization as an isolated,
read-only capability.

## Decision: adapt

The legacy DNA visualization is adapted, not copied and not reimplemented.
Data Analysis now provides a stable laclaugpt.multimethod.v1 contract containing
statement-level actor/concept coding, evidence identity, DNA projections, coverage,
and optional temporal/community products. Visualization consumes those outputs and
does not calculate actor/concept coding, projection weights, communities, or DNA
semantics.

If the artifact has no dna object, or if statement rows do not preserve
statement_id, actor_id, concept_id, and canonical source_url, the DNA view stays
disabled. There is deliberately no local fallback computation.

## Boundary and traceability

The isolated page is implemented in:

- dna_views.py: contract validation and bounded read-only tables;
- dna_page.py: Streamlit rendering and explicit descriptive caveats;
- pages/2_DNA.py: independent page entry point.

Actor-concept statement rows retain the upstream statement ID and source_url.
The evidence panel reconnects those URLs to the canonical Visualization frame, so
the source record remains inspectable without changing record identity.

## Rendering safety

Tables are bounded to 500 rows by default and 5000 rows maximum. This is a
presentation limit only. It does not alter Analysis output.

The UI explicitly states that congruence is not ideological identity, conflict is
not automatically political antagonism, weight/frequency is not importance, and
network structure is not evidence of hegemony.

## Rollback

The capability is isolated behind pages/2_DNA.py. Removing that page and the two
DNA modules returns the preceding Phase 1 baseline without changing Phase 0
list/inspect/export behavior or canonical adapters.
