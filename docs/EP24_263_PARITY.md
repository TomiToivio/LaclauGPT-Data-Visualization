# EP24 issue #263: legacy workbench parity, read-only increment

The legacy :8501 service is the reference. The reprocessed :8502 service is a separate deployment. This document describes **code in this repository**, not proof of deployment.

## Legacy surface matrix

| Legacy per-record tab | :8502 read-only view | Producer |
| --- | --- | --- |
| Metadata | Legacy record workbench / Metadata | country, source_type, account_type, URL, dates, duration, preference |
| Whisper | Legacy record workbench / Whisper | asr_transcript, asr_translation |
| OCR | Legacy record workbench / OCR | ocr_1 |
| Multimodal | Legacy record workbench / Multimodal | frame_analysis_1, vllm_video_analysis |
| Summary | Legacy record workbench / Summary | summary_analysis, summary_summary_md |
| Populism | Legacy record workbench / Populism | formula_of_populism_analysis and exported Laclau evidence |
| Themes | Legacy record workbench / Themes | postprocess_themes and normalized themes children when joinable |
| Persons | Legacy record workbench / Persons | postprocess_entities and normalized entities children, **not equivalent to a curated persons list** |
| Report Problems / Researcher Notes | Read-only annotation text, explicit unsaved warning | researcher_note, if present |

| Legacy corpus tab | :8502 read-only view | Caveat |
| --- | --- | --- |
| Frequency | Legacy corpus aggregates / Frequency | Preference counts; sum of numeric duration only |
| Entities | Legacy corpus aggregates / Entities | Top normalized entity labels counted per distinct matched video; fallback row-level coverage if child table unavailable |
| Topics | **Unavailable** | No LDA topic source |
| Sentiments | Legacy corpus aggregates / Sentiments | Availability of score fields, **not classified sentiment distribution** |
| Languages | Legacy corpus aggregates / Languages | Exported source language, not automatically Whisper-detected language |
| ManifestoBERTa | **Unavailable** | No predicted class source |
| Statistics | Legacy corpus aggregates / Statistics | Country, source type, account type, preference; country × preference table |
| Themes | Legacy corpus aggregates / Themes | Top normalized theme labels counted per distinct matched video; **not theme-over-time frequencies** |
| Persons | Legacy corpus aggregates / Persons | Entity coverage only; **not person-over-time frequencies** |

**Partial surfaces are deliberately described as partial.** Full aggregate parity needs validated normalized child label semantics, event-level dates, source-specific Whisper language and sentiment class codebooks. No model-based labels are synthesized by the UI. An absent producer must never become a zero.

## Operational and data limits

- Read-only: no MongoDB, private-repository annotation events, correction workflow, video edit or rerun request write-back. This requires a separate owner decision and audited contract.
- The backend currently supports multiple historical export layouts, but prioritizes the verified per-country layout when all three files are present. A future separately validated deployment should select a **single immutable per-country snapshot**; this PR does not change the host's selected snapshot.
- The private export manifest repair reported in issue #263 is tracked separately under private issue #77. This public PR does not rewrite private LFS objects or claim to have revalidated them.
- Keep the existing pipeline evidence inspector; scientific interpretations remain identified as model-generated interpretations.
- To verify a live update, follow `docs/EP24_8502_OPERATOR_CONTRACT.md`, including served SHA, password-gate verification, immutable snapshot identity, manifest checks, rendered real-data view and rollback.
- No AI26 code or deployment was changed. No deployment is performed by this PR.

## Remaining acceptance for #263

The full request is **not closed** until the partial aggregates are replaced by real source-backed legacy equivalents, the legacy filters are mapped and tested, canonical export layout and manifest are validated, reviewer write-back is explicitly decided and implemented if authorized, and the actual :8502 service passes the operator's deployment verification.
