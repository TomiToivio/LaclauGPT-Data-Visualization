#!/usr/bin/env bash
set -euo pipefail

: "${LACLAUGPT_VIS_ANALYSIS_DATA_DIR:?set LACLAUGPT_VIS_ANALYSIS_DATA_DIR to a private study-specific analysis directory}"

[[ -d "$LACLAUGPT_VIS_ANALYSIS_DATA_DIR" ]] || {
  echo "analysis data directory does not exist: $LACLAUGPT_VIS_ANALYSIS_DATA_DIR" >&2
  exit 2
}

export LACLAUGPT_VIS_PROFILE=${LACLAUGPT_VIS_PROFILE:-server}
export LACLAUGPT_VIS_DATA_DIR=${LACLAUGPT_VIS_DATA_DIR:-data}
export STREAMLIT_SERVER_ADDRESS=${STREAMLIT_SERVER_ADDRESS:-127.0.0.1}
export STREAMLIT_SERVER_PORT=${STREAMLIT_SERVER_PORT:-8501}
export STREAMLIT_SERVER_HEADLESS=${STREAMLIT_SERVER_HEADLESS:-true}
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

if [[ "$STREAMLIT_SERVER_ADDRESS" != "127.0.0.1" && "$STREAMLIT_SERVER_ADDRESS" != "localhost" && "$STREAMLIT_SERVER_ADDRESS" != "::1" ]]; then
  if [[ ${LACLAUGPT_VIS_ALLOW_NONLOOPBACK:-0} != 1 ]]; then
    echo "refusing non-loopback Streamlit bind without LACLAUGPT_VIS_ALLOW_NONLOOPBACK=1" >&2
    exit 2
  fi
fi

exec laclaugpt-visualize
