#!/usr/bin/env bash
set -euo pipefail

: "${LACLAUGPT_VIS_MONGODB_URI:?Set private MongoDB URI outside the repository}"
: "${LACLAUGPT_REDIS_URL:?Set private Redis URL outside the repository}"
: "${LACLAUGPT_VIS_S3_ENDPOINT_URL:?Set private S3/Allas endpoint outside the repository}"
: "${LACLAUGPT_VIS_S3_BUCKET:?Set private S3/Allas bucket outside the repository}"

export LACLAUGPT_VIS_PROJECT_ID="${LACLAUGPT_VIS_PROJECT_ID:-ai26}"
export LACLAUGPT_VIS_PROFILE="${LACLAUGPT_VIS_PROFILE:-server}"
export LACLAUGPT_VIS_MACHINE="${LACLAUGPT_VIS_MACHINE:-linux-server}"
export LACLAUGPT_VIS_EXECUTION="${LACLAUGPT_VIS_EXECUTION:-web-service}"
export LACLAUGPT_VIS_STORAGE="${LACLAUGPT_VIS_STORAGE:-distributed}"
export LACLAUGPT_VIS_STORAGE_BACKEND="${LACLAUGPT_VIS_STORAGE_BACKEND:-mongodb}"
export LACLAUGPT_VIS_DATA_BACKEND="${LACLAUGPT_VIS_DATA_BACKEND:-mongodb}"
export LACLAUGPT_VIS_CACHE_BACKEND="${LACLAUGPT_VIS_CACHE_BACKEND:-redis}"
export LACLAUGPT_VIS_MESSAGING_BACKEND="${LACLAUGPT_VIS_MESSAGING_BACKEND:-redis}"
export LACLAUGPT_VIS_OBJECT_BACKEND="${LACLAUGPT_VIS_OBJECT_BACKEND:-s3}"
export LACLAUGPT_VIS_SERVER_HOST="${LACLAUGPT_VIS_SERVER_HOST:-127.0.0.1}"
export LACLAUGPT_VIS_SERVER_PORT="${LACLAUGPT_VIS_SERVER_PORT:-8501}"

if [[ "$LACLAUGPT_VIS_PROJECT_ID" != "ai26" ]]; then
  echo "AI26 dashboard refuses project_id=$LACLAUGPT_VIS_PROJECT_ID" >&2
  exit 2
fi

exec streamlit run src/laclaugpt_visualization/ai26_dashboard.py \
  --server.address "$LACLAUGPT_VIS_SERVER_HOST" \
  --server.port "$LACLAUGPT_VIS_SERVER_PORT" \
  --server.headless true \
  --server.enableCORS true \
  --server.enableXsrfProtection true
