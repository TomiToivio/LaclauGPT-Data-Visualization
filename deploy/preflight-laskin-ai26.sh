#!/usr/bin/env bash
set -euo pipefail

PUBLIC_ROOT=/mnt/workspace/LaclauGPT-Data-Visualization
PRIVATE_ROOT=/mnt/workspace/LaclauGPT-Private
PRIVATE_ENV="$PRIVATE_ROOT/config/ai26/visualization/laskin.env"
VENV="$PUBLIC_ROOT/.venv"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf 'OK: %s\n' "$*"; }

cd "$PUBLIC_ROOT" || fail "cannot enter $PUBLIC_ROOT"
[[ "$(pwd -P)" == "$PUBLIC_ROOT" ]] || fail "pwd is not $PUBLIC_ROOT"
[[ "$(git rev-parse --show-toplevel)" == "$PUBLIC_ROOT" ]] || fail "git root is not $PUBLIC_ROOT"
info "public checkout path verified"

[[ -d "$PRIVATE_ROOT" ]] || fail "private root missing: $PRIVATE_ROOT"
[[ -f "$PRIVATE_ENV" ]] || fail "private environment missing: $PRIVATE_ENV"
info "private AI26 environment exists"

[[ -x "$VENV/bin/laclaugpt-visualize" ]] || fail "visualization virtualenv/CLI missing under $VENV"
info "visualization CLI installed"

# systemd EnvironmentFile syntax is shell-compatible for the simple KEY=VALUE contract used here.
set -a
# shellcheck disable=SC1090
source "$PRIVATE_ENV"
set +a

[[ "${LACLAUGPT_VIS_PROJECT_ID:-}" == "ai26" ]] || fail "LACLAUGPT_VIS_PROJECT_ID must be ai26"
[[ "${LACLAUGPT_VIS_MACHINE:-}" == "linux-server" ]] || fail "machine must be linux-server"
[[ "${LACLAUGPT_VIS_STORAGE:-}" == "distributed" ]] || fail "storage must be distributed"
[[ "${LACLAUGPT_VIS_DATA_BACKEND:-}" == "mongodb" ]] || fail "data backend must be mongodb"
[[ "${LACLAUGPT_VIS_CACHE_BACKEND:-}" == "redis" ]] || fail "cache backend must be redis"
[[ "${LACLAUGPT_VIS_MESSAGING_BACKEND:-}" == "redis" ]] || fail "messaging backend must be redis"
[[ "${LACLAUGPT_VIS_SERVER_HOST:-127.0.0.1}" != "0.0.0.0" ]] || fail "refusing wildcard bind without an explicit protected access layer"
info "AI26 distributed profile shape verified"

# These commands emit only the application's sanitized profile/readiness output.
"$VENV/bin/laclaugpt-visualize" profile
"$VENV/bin/laclaugpt-visualize" health

info "sanitized AI26 Laskin preflight passed"
