#!/usr/bin/env bash
# Run on the authorized Pouta host; never changes firewall or other services.
set -euo pipefail
MODE="${1:-check}"
: "${EP24_CODE_DIR:?Set EP24_CODE_DIR to the public code checkout}"
: "${EP24_PRIVATE_DIR:?Set EP24_PRIVATE_DIR to the private checkout}"
: "${LACLAUGPT_VIS_ANALYSIS_DATA_DIR:?Set the versioned private snapshot directory}"
SERVICE=laclaugpt-ep24-researcher
case "$MODE" in
  code) git -C "$EP24_CODE_DIR" pull --ff-only ;;
  data) git -C "$EP24_PRIVATE_DIR" pull --ff-only; git -C "$EP24_PRIVATE_DIR" lfs pull ;;
  check|restart) ;;
  *) echo 'Usage: deploy_pouta_ep24.sh check|code|data|restart' >&2; exit 2 ;;
esac
"$EP24_CODE_DIR/.venv-ep24/bin/python" - <<'PY'
import json
import os
from pathlib import Path
import pandas as pd
from laclaugpt_visualization.ep24_cohort import read_roster, is_member
root = Path(os.environ['LACLAUGPT_VIS_ANALYSIS_DATA_DIR'])
private = Path(os.environ['EP24_PRIVATE_DIR']).resolve()
assert root.resolve().is_relative_to(private), 'Snapshot must be inside private checkout'
manifest = json.loads((root / 'MANIFEST.json').read_text())
cohort = manifest.get('approved_cohort', {})
assert cohort.get('schema') == 'ep24-approved-cohort/1', 'Approved cohort manifest required'
assert cohort.get('approved_counts') == dict.fromkeys(('finland', 'poland', 'portugal'), 500)
roster = Path(os.environ.get('EP24_APPROVED_ROSTER', str(private / 'analysis/ep24_reprocess/sample_roster/monday500_roster.txt')))
approved, roster_manifest = read_roster(roster)
assert roster_manifest['sha256'] == cohort['sha256'], 'Roster checksum mismatch'
frame = pd.read_csv(root / 'combined.csv')
assert all(is_member(row, str(row['country']).lower(), approved)
           for row in frame.to_dict(orient='records')), 'Unapproved cohort member'
counts = frame['country'].str.lower().value_counts().to_dict()
assert counts == cohort['exported_counts'], 'Manifest counts disagree with snapshot'
assert all(n == 500 for n in counts.values()) and len(counts) == 3, 'Incomplete cohort snapshot'
assert frame['_storage_id'].nunique() == 1500, 'Duplicate/missing cohort identities'
assert all(str(v).startswith('monday500:' + str(c).lower() + ':')
           for v, c in zip(frame['_storage_id'], frame['country'], strict=True))
print('Verified cohort counts:', counts)
print('Approved roster SHA256:', cohort['sha256'])
PY
if [[ "$MODE" == restart ]]; then
  systemctl --user restart "$SERVICE"
  curl --fail --retry 10 --retry-delay 1 --max-time 5 http://127.0.0.1:8502/_stcore/health
fi
git -C "$EP24_CODE_DIR" rev-parse HEAD
git -C "$EP24_PRIVATE_DIR" rev-parse HEAD
