# EP24 dashboard refresh procedure (#210)

**Repeatable, and repeatable is the point.** This is the procedure actually run on 2026-10-28,
with its real outputs. It refreshes the FI/PL/PT researcher dashboard from the latest
Multimodal-Analysis outputs.

## 1. What "refresh" means here

The dashboard does not query MongoDB. It reads a **canonical export** produced by the
Multimodal-Analysis exporter. A refresh is therefore: re-export, verify, repoint, verify again.

**Data never enters this repository.** The export lives in `LaclauGPT-Private`; this repo holds
the procedure and the code that reads it.

## 2. Export

```bash
cd /mnt/workspace/LaclauGPT-Multimodal-Analysis
set -a && . /mnt/workspace/LaclauGPT-Data-Analysis/.env && set +a
export LACLAUGPT_MONGO_URI="$LACLAUGPT_MONGODB_URI"
export LACLAUGPT_MONGO_DATABASE="$LACLAUGPT_MONGODB_DATABASE"

python scripts/ep24/export_mongo_results.py \
  --country finland poland portugal \
  --output /mnt/workspace/LaclauGPT-Private/analysis/ep24/mongo_export_$(date +%j)
```

**Do not wrap this in a short timeout.** A 500-second cap cut a run off mid-way on 2026-10-28
after Finland and Poland, leaving no manifest and no Portugal — which reads as a silent data
loss if nobody checks. The full run takes roughly 10 minutes.

## 3. Verify before repointing

```bash
python scripts/ep24/report_stage_coverage.py \
  --export-dir <export-dir> --json <export-dir>/stage_coverage.json --md <export-dir>/STAGE_COVERAGE.md
```

Check in `MANIFEST.json`: `read_only: true`, `records`, and per-country `records` /
`source_documents` / `quarantined`. **A refresh that changes the record count is a different
event from one that changes the values** — both are legitimate, and they mean different things.

### What happened on 2026-10-28

| | previous export | refresh |
|---|---|---|
| generated | 2026-10-27T07:56:02Z | **2026-10-28T14:09:48Z** |
| records | 4,866 | **4,866** |
| FI / PL / PT | 2,125 / 1,781 / 960 | **2,125 / 1,781 / 960** |
| quarantined | 0 | **0** |

**Identical row count, identical `record_id` set, identical column set, identical row order — and
a different file hash.** That combination means the *values* were updated for the same videos:
newer analysis output for the same corpus. Comparing counts alone would have concluded "nothing
changed", which is exactly the wrong conclusion.

## 4. Repoint and verify

```bash
LACLAUGPT_VIS_ANALYSIS_DATA_DIR=<export-dir> \
LACLAUGPT_VIS_PROJECT_ID=ep24 \
LACLAUGPT_VIS_PROFILE=server \
LACLAUGPT_VIS_ALLOW_NONLOOPBACK=1 \
STREAMLIT_SERVER_ADDRESS=100.115.95.109 \
python -m streamlit run src/laclaugpt_visualization/ep24_reprocessed_app.py --server.port 18502
```

Then check, in order:

1. `curl -o /dev/null -w "%{http_code}" http://100.115.95.109:18502/` → **200**
2. `curl http://100.115.95.109:18502/_stcore/health` → **ok**
3. the page renders **"4866 records in this export"** with country scope **Finland (2125),
   Poland (1781), Portugal (960)** — the numbers read off the manifest, not off memory

All three were verified after this refresh.

## 5. Why the dashboard was repointed rather than left alone

Same counts, updated values. Leaving the old directory would have kept the dashboard on stale
analysis for an identical-looking corpus — the precise failure the issue was filed about.

## 6. Known limitations

- The canonical CSV **drops the largest text fields**; text surfaces live in the
  `*_text.jsonl.gz` bundles. A step that reads 0 % in `STAGE_COVERAGE.md` may be fully processed
  with its prose stored elsewhere. The coverage report states which measure it is using.
- Step 9 (RDF) is not a CSV column and is reported as *not carried*, not as zero.
- The dashboard is a foreground process, not a systemd unit. A reboot ends it; this procedure
  restarts it.
