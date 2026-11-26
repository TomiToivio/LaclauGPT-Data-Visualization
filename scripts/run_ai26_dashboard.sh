#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PY="$ROOT_DIR/.venv/bin/python"
[[ -x "$PY" ]] || { echo "AI26 dashboard virtualenv missing: $PY" >&2; exit 2; }

: "${LACLAUGPT_VIS_MONGODB_URI:?Set private MongoDB URI outside the repository}"
: "${LACLAUGPT_REDIS_URL:?Set private Redis URL outside the repository}"

export LACLAUGPT_VIS_PROJECT_ID="${LACLAUGPT_VIS_PROJECT_ID:-ai26}"
export LACLAUGPT_VIS_PROFILE="${LACLAUGPT_VIS_PROFILE:-server}"
export LACLAUGPT_VIS_MACHINE="${LACLAUGPT_VIS_MACHINE:-linux-server}"
export LACLAUGPT_VIS_EXECUTION="${LACLAUGPT_VIS_EXECUTION:-web-service}"
export LACLAUGPT_VIS_STORAGE="${LACLAUGPT_VIS_STORAGE:-distributed}"
export LACLAUGPT_VIS_STORAGE_BACKEND="${LACLAUGPT_VIS_STORAGE_BACKEND:-mongodb}"
export LACLAUGPT_VIS_DATA_BACKEND="${LACLAUGPT_VIS_DATA_BACKEND:-mongodb}"
export LACLAUGPT_VIS_CACHE_BACKEND="${LACLAUGPT_VIS_CACHE_BACKEND:-redis}"
export LACLAUGPT_VIS_MESSAGING_BACKEND="${LACLAUGPT_VIS_MESSAGING_BACKEND:-redis}"
export LACLAUGPT_VIS_OBJECT_BACKEND="${LACLAUGPT_VIS_OBJECT_BACKEND:-local}"
export LACLAUGPT_VIS_SERVER_HOST="${LACLAUGPT_VIS_SERVER_HOST:-127.0.0.1}"
export LACLAUGPT_VIS_SERVER_PORT="${LACLAUGPT_VIS_SERVER_PORT:-8504}"

if [[ "$LACLAUGPT_VIS_PROJECT_ID" != "ai26" ]]; then
  echo "AI26 dashboard refuses project_id=$LACLAUGPT_VIS_PROJECT_ID" >&2
  exit 2
fi

cd "$ROOT_DIR"
exec "$PY" -m streamlit run src/laclaugpt_visualization/ai26_dashboard.py \
  --server.address "$LACLAUGPT_VIS_SERVER_HOST" \
  --server.port "$LACLAUGPT_VIS_SERVER_PORT" \
  --server.headless true \
  --server.enableCORS true \
  --server.enableXsrfProtection true
