#!/usr/bin/env bash
# Serve the EP24 FI/PL/PT researcher dashboard on Laskin (issue #242, target :8502).
#
# The app is public code; the artifacts are private data. Point the app at the artifact root with
# LACLAUGPT_VIS_LIVE_STEPS_DATA - never at a path inside this repository.
#
#   LACLAUGPT_VIS_LIVE_STEPS_DATA=... scripts/ep24/serve_researcher_dashboard.sh [port] [address]
#
# Defaults: port 8502, address 127.0.0.1. Bind to the Tailscale address (100.115.95.109) for
# researcher access; 0.0.0.0 puts unauthenticated research data on every interface, so it is refused.
# :8501 (AI26) and :8503 (live steps operations) are other services: this script never touches them.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${1:-8502}"
ADDRESS="${2:-127.0.0.1}"
PYTHON="${LACLAUGPT_VIS_PYTHON:-${ROOT}/.venv/bin/python}"

if [[ -z "${LACLAUGPT_VIS_LIVE_STEPS_DATA:-}" ]]; then
  echo "LACLAUGPT_VIS_LIVE_STEPS_DATA is not set: it must point at the private artifact directory" >&2
  exit 2
fi
if [[ ! -f "${LACLAUGPT_VIS_LIVE_STEPS_DATA}/MANIFEST.json" ]]; then
  echo "no MANIFEST.json under ${LACLAUGPT_VIS_LIVE_STEPS_DATA}" >&2
  exit 2
fi
if [[ ! -x "${PYTHON}" ]]; then
  echo "python not found at ${PYTHON}; set LACLAUGPT_VIS_PYTHON" >&2
  exit 2
fi
if [[ "${ADDRESS}" == "0.0.0.0" || "${ADDRESS}" == "::" ]]; then
  echo "refusing to bind ${ADDRESS}: the artifacts contain transcripts and usernames" >&2
  exit 2
fi
for reserved in 8501 8503; do
  if [[ "${PORT}" == "${reserved}" ]]; then
    echo "refusing to take :${reserved}; that service belongs to another deployment" >&2
    exit 2
  fi
done

export LACLAUGPT_VIS_LIVE_STEPS_DATA
export PYTHONUNBUFFERED=1
exec "${PYTHON}" -m streamlit run \
  "${ROOT}/src/laclaugpt_visualization/live_steps_app.py" \
  --server.address "${ADDRESS}" \
  --server.port "${PORT}" \
  --server.headless true \
  --browser.gatherUsageStats false
