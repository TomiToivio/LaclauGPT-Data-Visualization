#!/usr/bin/env bash
# AI26 Phase 2 visualization preflight for the NooPunk node (issue LaclauGPT#71).
#
# NooPunk is the always-on browser collection node and the on-demand test
# workstation; Laskin remains the always-on analysis/visualization node. This
# preflight therefore checks the same AI26 contract as the Laskin preflight, plus
# the two things that are specific to a test node: it must NOT identify as Laskin,
# and it must stay bound to localhost rather than becoming a public service.
#
# It intentionally does not verify reachability of the shared MongoDB/Redis/Allas
# endpoints. Those are optional capabilities that live in the private environment;
# the sanitized `laclaugpt-visualize health` command below reports them as
# available/degraded, which is the correct behaviour when a shared service is
# temporarily unreachable. A preflight that hard-failed on a remote service would
# make an offline workstation unusable for exactly the testing it exists for.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PUBLIC_ROOT="${LACLAUGPT_VIS_REPO_ROOT:-$(cd -- "$SCRIPT_DIR/.." && pwd -P)}"
PRIVATE_ENV="${LACLAUGPT_VIS_ENV_FILE:-}"
VENV="${LACLAUGPT_VIS_VENV:-$PUBLIC_ROOT/.venv}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf 'OK: %s\n' "$*"; }

[[ -n "$PRIVATE_ENV" ]] || fail "LACLAUGPT_VIS_ENV_FILE must point to the private NooPunk AI26 environment file"
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

# --- the shared AI26 contract, identical to Laskin ---
[[ "${LACLAUGPT_VIS_PROJECT_ID:-}" == "ai26" ]] || fail "LACLAUGPT_VIS_PROJECT_ID must be ai26"
[[ "${LACLAUGPT_VIS_BROWSER_DATA_CONTRACT:-}" == "canonical" ]] || fail "browser data contract must be canonical"

# --- the NooPunk-specific runtime policy ---
# `machine` is a CLASS of machine, not a hostname: the field accepts only
# laptop|linux-server|custom, and the distributed-run schema's machine_role uses
# laptop|roihu|linux-server. NooPunk is an interactive workstation, so its class is
# `laptop`; Laskin's is `linux-server`. Requiring the class rather than a hostname is
# deliberate -- neither field is meant to carry host identity, and inventing a
# "noopunk" value here would be rejected by the application's own settings model.
[[ "${LACLAUGPT_VIS_MACHINE:-}" == "laptop" ]] || fail "LACLAUGPT_VIS_MACHINE must be laptop on NooPunk (an interactive workstation); Laskin uses linux-server"
[[ "${LACLAUGPT_VIS_EXECUTION:-}" == "web-service" ]] || fail "execution must be web-service"

# A test surface on an interactive workstation must not listen on a wildcard
# address. This matters more here than on Laskin: NooPunk is user-facing.
[[ "${LACLAUGPT_VIS_SERVER_HOST:-127.0.0.1}" != "0.0.0.0" ]] || fail "refusing wildcard bind without a protected access layer"
info "AI26 Phase 2 NooPunk profile shape verified"

# The dashboard must read the shared corpus, not a machine-local fork of it. A
# local-files-only configuration would silently show an empty or stale corpus while
# looking healthy, which is the failure this check exists to catch.
if [[ "${LACLAUGPT_VIS_DATA_BACKEND:-}" == "files" && "${LACLAUGPT_VIS_NOOPUNK_ALLOW_LOCAL_ONLY:-}" != "1" ]]; then
  fail "LACLAUGPT_VIS_DATA_BACKEND=files on the NooPunk node would fork the corpus; \
set LACLAUGPT_VIS_NOOPUNK_ALLOW_LOCAL_ONLY=1 only for a deliberate offline UI test"
fi
info "shared-corpus backends selected"

# Starting the UI must not start analysis. NooPunk must never claim shared analysis
# work as a side effect of a testing session, because that would take it from Laskin.
if [[ -n "${LACLAUGPT_VIS_ANALYSIS_AUTOSTART:-}" ]]; then
  fail "LACLAUGPT_VIS_ANALYSIS_AUTOSTART must not be set on NooPunk; the dashboard is a read surface"
fi
info "analysis autostart is off (dashboard cannot enqueue work)"

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

info "sanitized AI26 NooPunk preflight passed"
