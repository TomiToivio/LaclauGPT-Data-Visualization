#!/usr/bin/env bash
# Read-only host check. Run before starting Streamlit and after migration/reboot.
set -euo pipefail
mode=${1:?expected before-start or serving}
case "$mode" in before-start|serving) ;; *) exit 2 ;; esac
: "${LACLAUGPT_VIS_SERVER_HOST:?set the authorized tailnet IPv4 address}"
[[ ${LACLAUGPT_VIS_SERVER_PORT:-} == 8504 ]] || { echo 'Expected port 8504' >&2; exit 1; }
tailnet_ip=$(tailscale ip -4)
[[ "$LACLAUGPT_VIS_SERVER_HOST" == "$tailnet_ip" ]] || {
  echo 'Configured bind differs from the local Tailscale IPv4 address' >&2
  exit 1
}
listeners=$(ss -H -ltn '( sport = :8501 or sport = :8502 or sport = :8503 or sport = :8504 )')
endpoints=$(awk 'NF {print $4}' <<< "$listeners")
if [[ "$mode" == before-start && -n "$endpoints" ]]; then
  echo 'A listener still occupies a dashboard port' >&2
  exit 1
fi
if [[ "$mode" == serving && "$endpoints" != "$tailnet_ip:8504" ]]; then
  echo 'Expected exactly one dashboard listener, bound to the tailnet address on 8504' >&2
  exit 1
fi
