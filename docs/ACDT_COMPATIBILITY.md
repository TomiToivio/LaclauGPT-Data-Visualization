# AC/DT backwards compatibility

This repository implements the visualization side of `TomiToivio/LaclauGPT#36`.

The shared stable method IDs and result envelope are defined by the core repository's `schemas/acdt_method_registry.v1.yaml` and `schemas/acdt_result.v1.schema.json`.

## Result adapters

`src/laclaugpt_visualization/acdt_compat.py` accepts both current `acdt-result/1.0` envelopes and older plugin-shaped results. Missing legacy metadata is rendered as `not_available`; it is never guessed.

The adapter projects shared results into the existing backend-neutral `DataProduct` types:

- topic/thematic/frequency/keyness/sentiment/emotion/intensity/scaling results -> `TABLE`
- temporal peak results -> `TIMELINE`
- hashtag/SNA/DNA results -> `NETWORK`
- close-reading samples -> `RECORDS`
- multimodal rhetoric-performative results -> `RECORDS` plus `MEDIA`

`src/laclaugpt_visualization/acdt_provider.py` implements a `ProductProvider` over one or more result envelopes, so the existing visualization plugin registry can render them without a storage-specific backend.

## Provenance panel

Every projected product carries:

- schema version
- stable method ID/version
- interpretation mode
- study/corpus identifiers
- analysis provenance
- validation/human-review state
- a method-specific semantic warning

## Semantic safeguards

The dashboard must never relabel a visual pattern as a theoretical finding. In particular:

- network proximity/community/centrality is not ideology, articulation, equivalence or hegemony;
- sentiment/emotion/intensity is not affective investment;
- topic membership is not frame/discourse/ideology;
- a temporal peak is not hegemony;
- Wordscores/Wordfish coordinates are not ideological labels without substantive validation.

`theoretical_labels_authorized()` returns true only for an already theory-bearing `theoretical_interpretive` result whose human-review state is reviewed/accepted/canonical. It never generates a theoretical label.

## Legacy behaviour

Old datasets/results that lack new metadata remain renderable. The UI can show the available payload while explicitly marking schema/method/review fields as unavailable rather than failing or silently inventing values.

`tests/test_acdt_compat.py` covers legacy fallback, method/provenance metadata, product mapping and the semantic guardrails.