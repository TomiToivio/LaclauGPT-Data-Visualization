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

# Issue #53: the Visualization repository owns the live AI26 dashboard. The legacy
# Discourse-Analysis dashboard/export units must stay retired so no JSONL path is
# continuously written without a consumer.
if command -v systemctl >/dev/null 2>&1; then
  legacy_units=(ai26-dashboard.service ai26-export.service ai26-export.timer)
  active_legacy=()
  for unit in "${legacy_units[@]}"; do
    if systemctl --user is-active --quiet "$unit" 2>/dev/null; then
      active_legacy+=("$unit")
    fi
  done
  if (( ${#active_legacy[@]} > 0 )); then
    fail "legacy AI26 user units are still active: ${active_legacy[*]}; retire them before starting Visualization"
  fi
  info "legacy AI26 dashboard/export user units are inactive"
fi

# These commands emit only the application's sanitized profile/readiness output.
"$VENV/bin/laclaugpt-visualize" profile
"$VENV/bin/laclaugpt-visualize" health

info "sanitized AI26 Laskin preflight passed"
