#!/usr/bin/env bash
# Serve the FI/PL/PT live steps 1-7 researcher dashboard (issue #62).
#
# The app is public code; the artifacts are private data. Point the app at the artifact root with
# LACLAUGPT_VIS_LIVE_STEPS_DATA - never at a path inside this repository.
#
#   LACLAUGPT_VIS_LIVE_STEPS_DATA=... scripts/serve_live_steps.sh [port] [address]
#
# Defaults: port 8503, address 127.0.0.1. Bind to the Tailscale address for researcher access
# (Laskin is 100.115.95.109); 0.0.0.0 exposes unauthenticated research data on every interface.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8503}"
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

cd "${ROOT}"
exec "${PYTHON}" -m streamlit run src/laclaugpt_visualization/live_steps_app.py \
  --server.address "${ADDRESS}" --server.port "${PORT}" \
  --server.headless true --browser.gatherUsageStats false
