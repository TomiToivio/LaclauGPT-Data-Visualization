#!/usr/bin/env bash
# Serve the EP24 FI/PL/PT researcher dashboard on Laskin (issue #242, target :8502).
#
# The app is public code; the export is private data: 500 processed videos per country, read from
# LACLAUGPT_VIS_ANALYSIS_DATA_DIR - never a path inside this repository. No cohort roster is needed;
# a protected password and the actual combined.csv are.
#
#   LACLAUGPT_VIS_ANALYSIS_DATA_DIR=... scripts/ep24/serve_researcher_dashboard.sh [port] [address]
#
# Defaults: port 8502, address 127.0.0.1. Bind to the Tailscale address (100.115.95.109) for
# researcher access; 0.0.0.0 puts unauthenticated research data on every interface, so it is refused.
# :8501 (AI26) and :8503 (live steps operations) are other services: this script never touches them.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${1:-8502}"
ADDRESS="${2:-127.0.0.1}"
PYTHON="${LACLAUGPT_VIS_PYTHON:-${ROOT}/.venv/bin/python}"

if [[ -z "${LACLAUGPT_VIS_ANALYSIS_DATA_DIR:-}" ]]; then
  echo "LACLAUGPT_VIS_ANALYSIS_DATA_DIR is not set: it must point at the private export directory" >&2
  exit 2
fi
if [[ ! -f "${LACLAUGPT_VIS_ANALYSIS_DATA_DIR}/combined.csv" ]]; then
  echo "no combined.csv under ${LACLAUGPT_VIS_ANALYSIS_DATA_DIR}" >&2
  exit 2
fi
# The cohort roster is optional: the export is shown as measured (issue #242, Tomi 2026-11-16).
if [[ -n "${EP24_APPROVED_ROSTER:-}" && ! -f "${EP24_APPROVED_ROSTER}" ]]; then
  echo "EP24_APPROVED_ROSTER is set but missing: ${EP24_APPROVED_ROSTER}" >&2
  exit 2
fi
if [[ -z "${LACLAUGPT_VIS_DEMO_PASSWORD:-}" ]]; then
  echo "LACLAUGPT_VIS_DEMO_PASSWORD is not set: the export carries transcripts and usernames" >&2
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

export LACLAUGPT_VIS_ANALYSIS_DATA_DIR
export PYTHONUNBUFFERED=1
exec "${PYTHON}" -m streamlit run \
  "${ROOT}/src/laclaugpt_visualization/ep24_researcher_app.py" \
  --server.address "${ADDRESS}" \
  --server.port "${PORT}" \
  --server.headless true \
  --browser.gatherUsageStats false
