#!/usr/bin/env bash
set -euo pipefail
: "${LACLAUGPT_VIS_ANALYSIS_DATA_DIR:?Set a private exported data directory}"
[[ -d "$LACLAUGPT_VIS_ANALYSIS_DATA_DIR" ]] || { echo "Private data directory not found" >&2; exit 2; }
export STREAMLIT_SERVER_ADDRESS="${STREAMLIT_SERVER_ADDRESS:-127.0.0.1}"
export STREAMLIT_SERVER_PORT="${STREAMLIT_SERVER_PORT:-18512}"
export STREAMLIT_SERVER_HEADLESS=true
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
if [[ "$STREAMLIT_SERVER_ADDRESS" != "127.0.0.1" && "$STREAMLIT_SERVER_ADDRESS" != "localhost" && "$STREAMLIT_SERVER_ADDRESS" != "::1" ]]; then
  echo "Refusing public bind without authenticated reverse proxy" >&2
  exit 2
fi
exec streamlit run src/laclaugpt_visualization/ep24_reprocessed_app.py \
  --server.address "$STREAMLIT_SERVER_ADDRESS" --server.port "$STREAMLIT_SERVER_PORT"
