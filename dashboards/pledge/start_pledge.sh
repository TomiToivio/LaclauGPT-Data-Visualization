#!/usr/bin/env bash
# Start (or restart) the PLEDGE dashboard on port 8501.
#
# Why this script exists: restarting with `pkill -f "streamlit run pledge_dashboard.py"` in an SSH
# one-liner kills the SSH command itself, because the pattern matches its own command line — the
# app then stays down and the caller sees an empty result. Killing the PID that owns the port is
# unambiguous, and setsid keeps the app alive after the SSH session ends.
set -u

PORT="${1:-8501}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=/usr/bin/python3.10

owner_pid() {
  ss -ltnp 2>/dev/null | awk -v port=":${PORT} " '$0 ~ port {print}' \
    | grep -oE 'pid=[0-9]+' | cut -d= -f2 | head -1
}

PID="$(owner_pid)"
if [ -n "${PID:-}" ]; then
  echo "stopping pid ${PID} on :${PORT}"
  kill "${PID}" 2>/dev/null || true
  for _ in $(seq 1 20); do
    ss -ltn 2>/dev/null | grep -q ":${PORT} " || break
    sleep 1
  done
fi

cd "${DIR}" || exit 1
setsid nohup "${PY}" -m streamlit run pledge_dashboard.py \
  --server.port "${PORT}" --server.headless true --server.address 0.0.0.0 \
  --browser.gatherUsageStats false > "/tmp/pledge_app.log" 2>&1 < /dev/null &

for _ in $(seq 1 30); do
  sleep 1
  if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/_stcore/health")" = "200" ]; then
    echo "pledge dashboard healthy on :${PORT}"
    exit 0
  fi
done

echo "pledge dashboard did not become healthy; last log lines:"
tail -5 /tmp/pledge_app.log
exit 1
