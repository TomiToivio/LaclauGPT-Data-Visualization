# EP24 FI/PL/PT researcher dashboard on Laskin (:8502)

## Processed-video export mode (#242, November 2026)

The researcher dashboard now consumes the **existing exported 500 processed videos for each of Finland, Poland and Portugal**, without an approved cohort roster or `EP24_APPROVED_ROSTER`. The export directory must contain `combined.csv` and the normal optional source manifest. This is deliberately not a source-population selection operation: prepare the 500-per-country CSV export upstream and point `LACLAUGPT_VIS_ANALYSIS_DATA_DIR` to it.

The app validates the loaded rows (500 per country; 1,500 total; no blank/duplicate country-scoped video identities) and checks manifest counts where supplied. It refuses mismatching exports rather than silently taking the first 500 rows of a larger data set. Stages 7/8/9 can be incomplete; the dashboard displays recorded coverage, not assumed completion. Researcher display allowlists and password-based access remain mandatory.

On the configured Laskin host, after authorized installation of the code and the private 1,500-row export, verify the records and restart only the researcher service. Never replace the :8503 live-steps service or the separate :8504 population dashboard. Record served commit, manifest, stage coverage and health before closing #242.


The researcher-facing dashboard for the 500-video EP24 test cohort. Issue
[#242](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/issues/242) targets CSC Pouta at
`http://86.50.228.141:8502/`; **on Tomi's instruction the deployment is on Laskin instead** — the
same service, the same data contract, the same acceptance checks, different host. The Pouta runbook
(`docs/EP24_POUTA.md`) stays as the reference for the reprocessed corpus; this one is authoritative
for the live-steps cohort.

| | |
| --- | --- |
| URL | `http://100.115.95.109:8502/` (Tailscale address of `laskin01`) |
| Code | `LaclauGPT-Data-Visualization@main` |
| App | `src/laclaugpt_visualization/ep24_researcher_app.py` |
| Data | `analysis/ep24/pouta_exports/fiplpt_500_20261115/` (checkpoint export + approved roster) |
| Service | `laclaugpt-ep24-researcher.service` (systemd **user** unit) |
| Neighbours | `:8501` AI26 dashboard, `:8503` live-steps operations — neither is touched |

## What the researcher sees

The corpus is 1 500 videos — Finland, Poland and Portugal, 500 each — from the
`ep24_monday500_20261031` run of the multimodal pipeline. The dashboard gates on an **approved
cohort roster** (`approved_cohort.txt`, 1 500 identities, digest recorded in the export manifest);
see `docs/EP24_COHORT_APPROVAL.md` for how it is built and what it proves. The app is read-only: it opens the export
files, never MongoDB, Redis, Slurm, a GPU or Ollama, and it writes nothing back.

Tabs: Overview · Videos & multimodal evidence · Entities and themes · Laclau discourse · DNA · SNA ·
Multilayer · RDF & methods · **Legacy analytics** · **Export**.

Coverage is a measurement, not a claim. In the 2026-11-10 build: steps 1–6 complete for all
1 500 videos, step 7 (DNA) complete for 500 of them, step 8 (SNA) partial, step 9 (RDF) not in the
frame. The UI states each of these; a stage the export lacks reads *unavailable in this source*,
never `0`.

## The export, and why it has its own gate

`src/laclaugpt_visualization/researcher_export.py` is the allowlist between the 126-column index and
a researcher's CSV. Three rules:

1. **Named columns only.** Identity, source metadata, stage statuses, findings and researcher notes
   are on the list; runtimes, GPU names, prompt versions, persistence flags, storage paths and
   orchestrator bookkeeping are dropped **with a reason**, and the reason travels into the export's
   provenance JSON.
2. **Default-deny for anything unknown.** A producer field added between builds is excluded, not
   leaked — and it is not allowed to take the dashboard down either.
3. **The drift is still reported.** `verify_researcher_dashboard.py` classifies the served corpus in
   strict mode, so an unclassified column fails the deployment check instead of quietly vanishing.

Each export download ships with `*.provenance.json`: dataset, manifest digest, served commit,
selection counts per country, the kept columns, and every dropped column with its reason.

## Deploy on a fresh host

```bash
git clone https://github.com/TomiToivio/LaclauGPT-Data-Visualization.git
cd LaclauGPT-Data-Visualization
python3 -m venv .venv && . .venv/bin/activate
python -m pip install -e .

# private data: place the artifact directory outside the repository
export LACLAUGPT_VIS_ANALYSIS_DATA_DIR=/path/to/private/analysis/ep24/pouta_exports/fiplpt_500_20261115
python scripts/ep24/verify_researcher_dashboard.py \
    --data-root "$LACLAUGPT_VIS_ANALYSIS_DATA_DIR"
```

Then the unit:

```bash
cp deploy/laclaugpt-ep24-researcher.service.example ~/.config/systemd/user/laclaugpt-ep24-researcher.service
# edit the three lines that name the host: repository path, artifact root, bind address
systemctl --user daemon-reload
systemctl --user enable --now laclaugpt-ep24-researcher.service
systemctl --user status laclaugpt-ep24-researcher.service
```

## Verify a deployment (do this, rather than trusting the green badge)

```bash
python scripts/ep24/verify_researcher_dashboard.py \
    --data-root "$LACLAUGPT_VIS_LIVE_STEPS_DATA" \
    --served-dir /path/to/served/checkout \
    --expected-commit "$(git -C /path/to/served/checkout rev-parse HEAD)" \
    --url http://100.115.95.109:8502
```

It checks, from the files and the process: the manifest parses and its totals agree with its own
per-country counts; three countries are exported; the CSV header classifies with no unclassified
column; the row count matches the manifest; the text bundles are present; every country reports stage
coverage; the served checkout is git and its tree is clean; the service answers
`/_stcore/health` with `ok`. Exit status = number of failures, so it can gate a deploy.

**A dirty served tree is a failure even when the commit hash is right**: it means the code being
served is not the commit being named.

## Exact approved-cohort validation (required before closing #242)

The default verifier checks the 1,500 total, country counts, field allowlist, stage
coverage and running service. **Those checks alone do not prove membership** in the
approved Monday500 cohort. The private repository also contains the authoritative
`analysis/ep24_reprocess/sample_roster/monday500_roster.txt` and the cleaned
per-country DataFrames under `analysis/live_steps_1_7/cleaned/`.

Run this additional fail-closed verification on an authorized checkout where Git LFS
artifacts are materialized:

```bash
python scripts/ep24/verify_researcher_dashboard.py \
    --data-root /path/to/LaclauGPT-Private/analysis/live_steps_1_7 \
    --approved-roster /path/to/LaclauGPT-Private/analysis/ep24_reprocess/sample_roster/monday500_roster.txt \
    --served-dir /path/to/served/visualization \
    --expected-commit "$(git -C /path/to/served/visualization rev-parse HEAD)" \
    --url http://100.115.95.109:8502
```

The membership check reads the canonical `_storage_id` column from the **private
cleaned DataFrames**, compares its exact 500 IDs per country with the approved
roster, and rejects duplicates, missing IDs, substituted videos or unreadable files.
It does **not** export those canonical storage identifiers to the researcher UI.

A passing legacy 16/16 check or a healthy HTTP endpoint cannot substitute for this
test. Record the verifier output and served revision in the issue before closing it.
If the cleaned DataFrames and dashboard index have been rebuilt at different times,
rebuild them from the same authoritative producer cohort before approval.

## Code update vs data update

They are separate, and should stay separate.

**Code** (the app changed, the data did not):

```bash
git -C /path/to/served/checkout pull --ff-only   # or check out the new commit
systemctl --user restart laclaugpt-ep24-researcher.service
python scripts/ep24/verify_researcher_dashboard.py ... --expected-commit <new sha>
```

**Data** (a new producer export landed): rebuild the private artifacts with
`tools/build_live_steps_artifacts.py --source-dir <producer csv dir> --out <artifact dir>`, then
restart the service so the cached frames are dropped, then re-run the verifier. The rebuild refuses to
finish while any source column is unclassified, which is what keeps the export gate meaningful.

## Rollback

`git -C /path/to/served/checkout checkout <previous sha> && systemctl --user restart
laclaugpt-ep24-researcher.service`. Data rollback is a directory rename: the artifacts are immutable
builds, so keep the previous build beside the new one instead of rebuilding in place.

## Access control

The service binds the Tailscale address, so reachability is membership of the tailnet. Do **not**
bind `0.0.0.0`: the corpus carries author usernames, video identifiers and verbatim transcripts.
For anyone outside the tailnet, put an authenticating reverse proxy in front; the app also supports
`LACLAUGPT_VIS_DEMO_PASSWORD`, which gates the UI before any data is read and keeps the password in
the environment, never in the repository.

## What this deployment does not yet claim

- Legacy parity is recorded per surface in `docs/EP24_LEGACY_PARITY_242.md`, verified against the
  legacy *source* and the deployed app. The live legacy `:8501` was not re-audited for this cohort,
  and ManifestoBERTa has no counterpart in this pipeline — both stated rather than papered over.
- Step 9 (RDF) has no representation in this cohort's artifacts, so the dashboard shows no
  knowledge-graph view for it rather than an empty one.
- Step 8 (SNA) is partial; the UI reports the coverage and the edge evidence, and does not infer ties
  the producer did not emit.
