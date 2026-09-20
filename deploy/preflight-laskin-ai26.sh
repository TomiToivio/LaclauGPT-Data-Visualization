#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PUBLIC_ROOT="${LACLAUGPT_VIS_REPO_ROOT:-$(cd -- "$SCRIPT_DIR/.." && pwd -P)}"
PRIVATE_ENV="${LACLAUGPT_VIS_ENV_FILE:-}"
VENV="${LACLAUGPT_VIS_VENV:-$PUBLIC_ROOT/.venv}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf 'OK: %s\n' "$*"; }

[[ -n "$PRIVATE_ENV" ]] || fail "LACLAUGPT_VIS_ENV_FILE must point to the private AI26 environment file"
[[ -f "$PRIVATE_ENV" ]] || fail "private environment file not found"

cd "$PUBLIC_ROOT" || fail "cannot enter configured visualization checkout"
PUBLIC_ROOT="$(pwd -P)"
[[ "$(git rev-parse --show-toplevel)" == "$PUBLIC_ROOT" ]] || fail "configured checkout is not the repository root"
info "visualization checkout verified"

[[ -x "$VENV/bin/laclaugpt-visualize" ]] || fail "visualization CLI missing from configured virtualenv"
info "visualization CLI installed"

set -a
# shellcheck disable=SC1090
source "$PRIVATE_ENV"
set +a

[[ "${LACLAUGPT_VIS_PROJECT_ID:-}" == "ai26" ]] || fail "LACLAUGPT_VIS_PROJECT_ID must be ai26"
[[ "${LACLAUGPT_VIS_BROWSER_DATA_CONTRACT:-}" == "canonical" ]] || fail "browser data contract must be canonical"
[[ "${LACLAUGPT_VIS_MACHINE:-}" == "linux-server" ]] || fail "machine must be linux-server"
[[ "${LACLAUGPT_VIS_EXECUTION:-}" == "web-service" ]] || fail "execution must be web-service"
[[ "${LACLAUGPT_VIS_SERVER_HOST:-127.0.0.1}" != "0.0.0.0" ]] || fail "refusing wildcard bind without a protected access layer"
info "AI26 Phase 1 profile shape verified"

# Optional distributed services are configuration choices. The application health command
# performs sanitized validation and must degrade cleanly when optional capabilities are absent.
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

"$VENV/bin/laclaugpt-visualize" profile
"$VENV/bin/laclaugpt-visualize" health

info "sanitized AI26 Laskin preflight passed"
