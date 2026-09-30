#!/usr/bin/env bash
# AI26 Phase 2 NooPunk node control wrapper (issue LaclauGPT#71).
#
# NooPunk is an interactive workstation, so its AI26 surfaces are user-activated
# rather than always on. This wrapper gives the three verbs per surface that the
# issue asks for, and deliberately does one thing less than an operator might
# expect: it never touches Laskin. The two nodes coordinate through the shared AI26
# contract, not through administrative control of each other.
#
# Usage:
#   ai26-noopunk.sh start  visualization
#   ai26-noopunk.sh stop   visualization
#   ai26-noopunk.sh status visualization
#
# Surfaces: visualization | analysis | collection
#
# analysis and collection are owned by their own repositories' runbooks; this
# wrapper shells out to them when present and reports honestly when they are not,
# rather than pretending the surface was controlled.
set -euo pipefail

SURFACE="${2:-}"
ACTION="${1:-}"
REPO_ROOT_ENV="${LACLAUGPT_VIS_REPO_ROOT:-}"
PID_DIR="${LACLAUGPT_NOOPUNK_RUN_DIR:-${XDG_RUNTIME_DIR:-/tmp}/laclaugpt-ai26-noopunk}"
LOG_DIR="${LACLAUGPT_NOOPUNK_LOG_DIR:-$PID_DIR/logs}"

usage() {
  cat >&2 <<'USAGE'
usage: ai26-noopunk.sh <start|stop|restart|status> <visualization|analysis|collection>

  start  visualization            start the AI26 dashboard for local testing
  start  analysis --model local   run a bounded analysis batch with gemma4:e2b
  start  analysis --model cloud   run a bounded analysis batch with gemma4:31b-cloud
  stop   analysis                 stop the analysis worker
  status visualization            report running state and effective contract

Cloud analysis is opt-in only and is never enabled implicitly.
USAGE
  exit 2
}

[[ -n "$SURFACE" ]] || usage

mkdir -p "$PID_DIR" "$LOG_DIR"

pid_file() { printf '%s/%s.pid\n' "$PID_DIR" "$1"; }

is_running() {
  local pf; pf="$(pid_file "$1")"
  [[ -f "$pf" ]] || return 1
  local pid; pid="$(cat "$pf" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

require_private_env() {
  [[ -n "${LACLAUGPT_VIS_ENV_FILE:-}" ]] || {
    printf 'ERROR: LACLAUGPT_VIS_ENV_FILE must point to the private NooPunk AI26 environment file\n' >&2
    exit 1
  }
}

# --------------------------------------------------------------------------
# visualization
# --------------------------------------------------------------------------
vis_start() {
  require_private_env
  if is_running visualization; then
    printf 'visualization already running (pid %s)\n' "$(cat "$(pid_file visualization)")"
    return 0
  fi
  # Fail closed: run the preflight rather than starting a misconfigured dashboard.
  bash "$(dirname -- "${BASH_SOURCE[0]}")/../deploy/preflight-noopunk-ai26.sh"
  (
    set -a
    # shellcheck disable=SC1090
    . "$LACLAUGPT_VIS_ENV_FILE"
    set +a
    exec "${LACLAUGPT_VIS_VENV:-${REPO_ROOT_ENV:-.}/.venv}/bin/laclaugpt-visualize" serve
  ) >"$LOG_DIR/visualization.log" 2>&1 &
  printf '%s\n' "$!" >"$(pid_file visualization)"
  printf 'visualization starting (pid %s); log: %s\n' "$!" "$LOG_DIR/visualization.log"
}

vis_stop() {
  if ! is_running visualization; then
    printf 'visualization not running\n'
    return 0
  fi
  local pid; pid="$(cat "$(pid_file visualization)")"
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$(pid_file visualization)"
  printf 'visualization stopped\n'
}

vis_status() {
  if is_running visualization; then
    printf 'visualization: running (pid %s)\n' "$(cat "$(pid_file visualization)")"
  else
    printf 'visualization: stopped\n'
  fi
  # Effective contract, when the CLI is available. Non-fatal: a stopped service with
  # an installed CLI is still worth reporting.
  local cli="${LACLAUGPT_VIS_VENV:-${REPO_ROOT_ENV:-.}/.venv}/bin/laclaugpt-visualize"
  if [[ -x "$cli" ]]; then
    "$cli" profile 2>/dev/null | sed 's/^/  /' || true
  fi
}

# --------------------------------------------------------------------------
# analysis (owned by LaclauGPT-Data-Analysis)
# --------------------------------------------------------------------------
analysis_cmd() {
  local repo="${LACLAUGPT_ANALYSIS_REPO_ROOT:-}"
  [[ -n "$repo" ]] || { printf 'ERROR: set LACLAUGPT_ANALYSIS_REPO_ROOT to the Analysis checkout\n' >&2; exit 1; }
  printf '%s/.venv/bin/laclaugpt-analysis-worker' "$repo"
}

analysis_start() {
  local model="local"
  shift || true
  while (( $# )); do
    case "$1" in
      --model) model="${2:-}"; shift 2 ;;
      --limited-batch) export LACLAUGPT_ANALYSIS_LIMITED_BATCH="${2:-}"; shift 2 ;;
      *) printf 'ERROR: unknown argument %s\n' "$1" >&2; exit 2 ;;
    esac
  done
  local worker; worker="$(analysis_cmd)"
  [[ -x "$worker" ]] || { printf 'ERROR: analysis worker not installed at %s\n' "$worker" >&2; exit 1; }
  case "$model" in
    local) export LACLAUGPT_OLLAMA_MODEL="${LACLAUGPT_OLLAMA_MODEL:-gemma4:e2b}" ;;
    cloud) export LACLAUGPT_OLLAMA_MODEL="${LACLAUGPT_OLLAMA_MODEL_cloud:-gemma4:31b-cloud}" ;;
    *) printf 'ERROR: --model must be local or cloud (got %s)\n' "$model" >&2; exit 2 ;;
  esac
  printf 'analysis model: %s (cloud is opt-in and never implicit)\n' "$LACLAUGPT_OLLAMA_MODEL" | tee "$LOG_DIR/analysis.model"
  "$worker" >"$LOG_DIR/analysis.log" 2>&1 &
  printf '%s\n' "$!" >"$(pid_file analysis)"
  printf 'analysis starting (pid %s); log: %s\n' "$!" "$LOG_DIR/analysis.log"
}

analysis_stop() {
  if ! is_running analysis; then printf 'analysis not running\n'; return 0; fi
  local pid; pid="$(cat "$(pid_file analysis)")"
  kill "$pid" 2>/dev/null || true
  rm -f "$(pid_file analysis)"
  printf 'analysis stopped\n'
}

analysis_status() {
  if is_running analysis; then
    printf 'analysis: running (pid %s)\n' "$(cat "$(pid_file analysis)")"
    [[ -f "$LOG_DIR/analysis.model" ]] && sed 's/^/  /' "$LOG_DIR/analysis.model"
  else
    printf 'analysis: stopped (off by default on this workstation)\n'
  fi
}

# --------------------------------------------------------------------------
# collection (owned by LaclauGPT-Data-Collection)
# --------------------------------------------------------------------------
collection_note() {
  printf 'collection is owned by the LaclauGPT-Data-Collection runbook; '
  printf 'it is the always-on surface on this node.\n'
}

case "$SURFACE" in
  visualization)
    case "$ACTION" in
      start)   vis_start ;;
      stop)    vis_stop ;;
      restart) vis_stop; vis_start ;;
      status)  vis_status ;;
      *) usage ;;
    esac ;;
  analysis)
    case "$ACTION" in
      start)  shift 2 2>/dev/null || true; analysis_start "$@" ;;
      stop)   analysis_stop ;;
      status) analysis_status ;;
      *) usage ;;
    esac ;;
  collection)
    collection_note ;;
  *) usage ;;
esac
