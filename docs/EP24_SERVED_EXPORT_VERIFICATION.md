# The served export is the release, or it is not (#263 §3)

The dashboard reads whatever directory its unit points at. Until this change, nothing compared that directory
with the artifact in the private repository, and twice the gap mattered:

* the private manifest declared a flat layout while the committed tree was per-country, so 26 of 28 declared
  files did not exist — a manifest answering "yes, this is the export" to a question nobody could check;
* the host served a `combined.csv` build whose bytes matched no committed file, so "the data on :8502" was an
  artefact of that host rather than a release.

## The check

```bash
python scripts/ep24/verify_served_export.py \
  --served /home/ubuntu/ep24_research/exports/fiplpt_500_20261115_release \
  --manifest /home/ubuntu/ep24_research/exports/fiplpt_500_20261115_release/manifest.json
```

Read-only. It reports every disagreement and exits non-zero when there is one:

| finding | why it matters |
| --- | --- |
| declared file missing from the served directory | the release is incomplete, or the unit points somewhere else |
| size differs | cheap first gate before hashing |
| SHA-256 differs | same name, different build — the case that started this |
| row count differs | a partial write or a filtered re-export |
| served but not declared | how a stale `combined.csv` or an old sidecar survives a layout change |

`--json` gives the same findings as data.

## What it found, and the state after

Run against the host's original directory, it reported **54 disagreements** — the flat layout the dashboard was
serving was not the per-country release at all. The private manifest was also three files short of its own
tree (the cohort, dictionary and qa sidecars were excluded by an extension filter); that was fixed in
LaclauGPT-Private#78, which now declares all 28 files.

The released layout was then copied to the host as `fiplpt_500_20261115_release`, verified, and the unit
pointed at it through a drop-in:

```ini
# ~/.config/systemd/user/ep24-dashboard-pouta.service.d/data-release.conf
[Service]
Environment=LACLAUGPT_VIS_ANALYSIS_DATA_DIR=/home/ubuntu/ep24_research/exports/fiplpt_500_20261115_release
```

```text
OK: .../fiplpt_500_20261115_release matches .../manifest.json (28 files)
records 1500 | created_at filled 1500 | children 11804
```

The previous flat snapshot stays on disk; removing the drop-in and restarting reverts the data root.

## Consequences for the layout question

There is now **one artifact layout** — per-country plus `children/`, described by `manifest.json` — and the
dashboard reads it in place rather than a rebuild. A `combined.csv` is no longer produced for deployment; when
a consumer needs one file it is generated from the release, not served beside it.

Run the check on the serving host after any data refresh, and before blaming a view for showing the wrong
records: a dashboard that loads 1,500 records from the wrong build looks exactly like one that loads them
from the right one.
