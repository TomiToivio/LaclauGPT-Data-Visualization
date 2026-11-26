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

# #234: the unit drifted off origin/main three times (#176, #185, #234) while this preflight
# stayed green, and a declared core dependency was missing from the serving venv. Assert both
# before the service is restarted: the checkout must be origin/main, and every requirement in
# [project].dependencies must be installed in the venv that will serve it. Deploying a branch on
# purpose requires LACLAUGPT_VIS_ALLOW_GIT_DRIFT=1, which is logged.
"$VENV/bin/python" "$PUBLIC_ROOT/deploy/preflight-checkout-ai26.py" \
  --repo-root "$PUBLIC_ROOT" --pyproject "$PUBLIC_ROOT/pyproject.toml" \
  || fail "serving checkout is not origin/main or its core dependencies are not installed (#234)"

set -a
# shellcheck disable=SC1090
source "$PRIVATE_ENV"
set +a

[[ "${LACLAUGPT_VIS_PROJECT_ID:-}" == "ai26" ]] || fail "LACLAUGPT_VIS_PROJECT_ID must be ai26"
[[ "${LACLAUGPT_VIS_BROWSER_DATA_CONTRACT:-}" == "canonical" ]] || fail "browser data contract must be canonical"
[[ "${LACLAUGPT_VIS_MACHINE:-}" == "linux-server" ]] || fail "machine must be linux-server"
[[ "${LACLAUGPT_VIS_EXECUTION:-}" == "web-service" ]] || fail "execution must be web-service"
[[ "${LACLAUGPT_VIS_SERVER_PORT:-}" == "8504" ]] || fail "AI26 Laskin deployment must explicitly select port 8504 (#330)"
# Direct access is restricted outside Streamlit. Reject public/wildcard binds;
# actual network ACLs still require host-side operator verification.
"$VENV/bin/python" - "${LACLAUGPT_VIS_SERVER_HOST:-}" <<'PY' || fail "set an explicit private IPv4 bind address"
import ipaddress
import sys

try:
    address = ipaddress.IPv4Address(sys.argv[1])
except ValueError:
    sys.exit(1)

networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")
sys.exit(0 if any(address in ipaddress.IPv4Network(net) for net in networks) else 1)
PY
[[ "${LACLAUGPT_VIS_NETWORK_ACCESS_VERIFIED:-}" == "1" ]] || fail "verify private network ACLs and set LACLAUGPT_VIS_NETWORK_ACCESS_VERIFIED=1"
# Ports reserved for retired dashboard deployments must be clear; never kill
# processes here. An operator must identify and stop the correct service.
command -v ss >/dev/null 2>&1 || fail "ss is required to inspect retired dashboard ports"
listeners="$(ss -H -ltn)" || fail "could not inspect listening TCP ports"
if printf '%s\n' "$listeners" | awk '$4 ~ /:(8501|8502|8503)$/ { found = 1 } END { exit !found }'; then
  fail "retired dashboard ports 8501–8503 still have listeners; inspect their owners"
fi
info "AI26 profile and retired dashboard ports verified"

# Optional distributed services are configuration choices. The application health command
# performs sanitized validation and must degrade cleanly when optional capabilities are absent.
if command -v systemctl >/dev/null 2>&1; then
  legacy_units=(laclaugpt-ai26-dashboard.service laclaugpt-visualization-ai26.service laclaugpt-ep24-researcher.service laclaugpt-live-steps.service ep24-fiplpt.service laclaugpt-ep24-mongo-demo.service laclaugpt-ep24-demo.service ep24-workbench-laskin.service laclaugpt-ep24-merge-lab.service)
  active_legacy=()
  for unit in "${legacy_units[@]}"; do
    if systemctl --user is-active --quiet "$unit" 2>/dev/null || systemctl --user is-enabled --quiet "$unit" 2>/dev/null; then
      active_legacy+=("$unit")
    fi
  done
  if (( ${#active_legacy[@]} > 0 )); then
    fail "retired dashboard user units are active or enabled: ${active_legacy[*]}; retire them before starting Visualization"
  fi
  info "retired dashboard user units are inactive"
fi

"$VENV/bin/laclaugpt-visualize" profile
"$VENV/bin/laclaugpt-visualize" health

info "sanitized AI26 Laskin preflight passed"
