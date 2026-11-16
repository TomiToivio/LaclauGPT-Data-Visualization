# Issue 242: researcher display and Monday500 delivery

This extends the existing reprocessed explorer and streaming exporter, and integrates
with `ep24_researcher_app.py` merged concurrently in PR #243. The service uses that
authenticated researcher entrypoint; no third app or export contract is introduced. Issue 242 remains open until the
real private snapshot and Pouta deployment are verified.

## Verified findings (2026-11-16)

- Read the legacy `ep2024_dashboard/dashboard.py`: metadata, Whisper, OCR,
  multimodal, summary, populism, themes, persons and annotation tabs; aggregate
  frequency, entities, topics, sentiment, languages, ManifestoBERTa and statistics.
- The legacy HTTP endpoint answered 200, but browser rendering timed out after
  showing only the Streamlit banner. **Visual/functional live parity is unverified.**
- The private repository contains an approved Monday500 roster and documents
  500 identities each for Finland, Poland and Portugal. Its dataset also holds
  additional full-corpus records: selecting by dataset name alone is insufficient.
- The existing private `analysis/ep24/dashboard/export/QA_REPORT.md` describes
  2,125 Finnish, 2,112 Polish and 1,069 Portuguese records, with legacy Polish and
  Portuguese inputs. That is **not** the requested Monday500 snapshot.
- No authorized SSH configuration/key is available in this workspace. No server
  changes, firewall changes or deployment verification were performed.

## Display contract

`ep24_presentation.FIELDS` is the versioned display/export allowlist
(`ep24-researcher-display/1`), also published in
`schemas/ep24_researcher_display_v1.json`. Structured child values are projected
through a nested key allowlist, then rendered as labelled text/lists. New producer
fields require explicit mapping. Default CSV exports escape spreadsheet formulas.
The source export remains unchanged for reproducibility.

Normal drilldown distinguishes source transcription/OCR, model interpretation and
researcher annotations. Full selected-record evidence is read lazily from either
flat `record_id` or stage-nested `record_key` gzip bundles. Diagnostics are disabled
unless the operator sets `LACLAUGPT_VIS_EP24_DIAGNOSTICS=1`; this is an operator
setting, not a substitute for authentication. Keep the existing password gate and
server-side access control when allowing diagnostics.

## Approved cohort export

Install the public package on the authorized export host. Use actual current
producer cumulative CSVs; do not substitute the old dashboard export.

```bash
python scripts/ep24/export_streaming.py \
  --source finland=/private/input/finland.csv \
  --source poland=/private/input/poland.csv \
  --source portugal=/private/input/portugal.csv \
  --approved-cohort /private/LaclauGPT-Private/analysis/ep24_reprocess/sample_roster/monday500_roster.txt \
  --output /private/LaclauGPT-Private/analysis/ep24/snapshots/monday500
```

The roster must contain exactly 500 unique namespaced IDs per country. Membership,
country and available dataset ID are checked **before** deduplication, so a more
complete unapproved row cannot replace an approved pilot row of the same video.
`--limit` is rejected with a roster. The manifest records roster SHA256, intended,
exported and missing counts. Missing analyses remain missing, never fabricated.
Normalized child tables append each country instead of overwriting earlier ones.

Commit permissioned snapshot files and their manifest in the private repository
only after inspecting counts, coverage and source provenance. Materialize Git LFS
objects (`git lfs pull`) before running; pointer files are not data. Snapshot
creation/commit and actual current completion counts remain blocked on readable
current producer outputs.

## Git-pull service workflow

Use `configs/ep24-researcher.env.example` with predictable public/private checkout
paths. Keep secrets in a server-local environment file, not either Git repository.
Create an isolated `.venv-ep24`, install the public package there, and freeze the
resolved environment into a private deployment lock file; use that lock for
subsequent installations. Do not silently reuse AI26's environment.

Install `deploy/laclaugpt-ep24-researcher.service.example` as a user service, adjust
paths, and enable it with `systemctl --user enable laclaugpt-ep24-researcher`.
Boot start additionally requires the host's approved user-service/linger policy.
The service binds **loopback :8502** and restarts on failure.

`scripts/deploy_pouta_ep24.sh` runs on the authorized host:

- `code`: fast-forward only the public checkout, then preflight the snapshot.
- `data`: fast-forward only the private checkout, materialize LFS, then preflight.
- `check`: validate cohort counts/identity and print both Git revisions.
- `restart`: preflight, restart only the distinct EP24 service, check local health.

For dependency changes, install from the reviewed private lock before restarting.
Logs: `journalctl --user -u laclaugpt-ep24-researcher`. For rollback, restore the
previous public revision and previous immutable snapshot path/environment lock,
then preflight and restart. Do not rewrite producer inputs or refresh live files
in place while the dashboard reads them.

Public exposure at the issue's requested Pouta address still requires the approved
network/access-control arrangement and TLS proxy or private VPN. This script never
opens firewall ports or changes legacy :8501 / AI26 :8503. Verify authenticated
navigation, exact served revision, manifest checksum, filters and real evidence
on the target host before marking deployment complete.

## Acceptance matrix (honest status)

| Legacy/requested capability | Implementation | Verification / remaining work |
| --- | --- | --- |
| Country/platform/language overview | Corpus overview bars, totals, date timeline | Synthetic AppTest; live visual audit pending |
| Country/platform/date filters | Existing sidebar reused | Existing filters retained |
| Search/sort/page/column chooser | Video browser; allowlisted fields only | AppTest and privacy tests |
| Filtered researcher CSV | Same display allowlist; formula escaping | Synthetic export regression |
| Transcript/OCR/summary | Friendly inspector with lazy full evidence | Both bundle shapes tested |
| Discourse | Readable concepts/evidence and summaries | Full producer vocabulary review still needed |
| DNA | Existing evidence resolver plus bounded bipartite plot | Existing child-link tests; live data pending |
| SNA | Bounded exported-evidence graph and selectable edge table | Requires source/target/type/quote; live outputs pending |
| Multilayer / RDF | Existing exploration retained | Rich RDF interpretation/downloads remain incomplete |
| Sentiment/topic/entity aggregates | Existing stage evidence retained | Dedicated parity charts still pending |
| Annotation / problem reporting | Existing annotations displayed | Editable annotation workflow still pending |
| ManifestoBERTa and specialised legacy plots | Not reproduced | Require available fields and explicit parity verification |
| Approved FI/PL/PT cohort | Roster-before-dedup filtering + manifest | Synthetic membership regression; real snapshot pending |
| Private Git-pull / Pouta :8502 | Isolated service, preflight/update script | SSH access and authorized smoke test pending |

Do not mark this document, the PR, or HTTP health alone as full issue completion.
