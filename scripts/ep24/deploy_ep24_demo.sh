#!/usr/bin/env bash
# Deploy the EP24 reprocessed demo to a host on a distinct port (issue #195).
#
#   scripts/ep24/deploy_ep24_demo.sh SpectacleScraper 8502 ~/work/LaclauGPT-Private/analysis/ep24/dashboard/export
#
# The demo is deliberately isolated: it does not touch AI26, the legacy :8501/:8503 services, or any
# other app on the host. Code goes to ~/ep24_demo/src, the private export to ~/ep24_demo/data.
set -euo pipefail

HOST="${1:?usage: deploy_ep24_demo.sh HOST PORT EXPORT_DIR}"
PORT="${2:?port required}"
EXPORT_DIR="${3:?export dir required}"
REMOTE_DIR="${REMOTE_DIR:-ep24_demo}"
PYTHON="${PYTHON:-python3}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_FILES=(
  "src/laclaugpt_visualization/__init__.py"
  "src/laclaugpt_visualization/ep24_reprocessed.py"
  "src/laclaugpt_visualization/ep24_reprocessed_app.py"
)

echo "== syncing code to $HOST:~/$REMOTE_DIR"
ssh "$HOST" "mkdir -p ~/$REMOTE_DIR/src/laclaugpt_visualization ~/$REMOTE_DIR/data"
for file in "${APP_FILES[@]}"; do
  scp -q "$REPO_ROOT/$file" "$HOST:~/$REMOTE_DIR/$file"
done

echo "== syncing private export (data stays out of Git)"
rsync -az --delete "$EXPORT_DIR/" "$HOST:~/$REMOTE_DIR/data/"

echo "== restarting streamlit on port $PORT (by PID, never by pattern)"
ssh "$HOST" "cd ~/$REMOTE_DIR
PID=\$(ss -ltnp 2>/dev/null | grep ':$PORT ' | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2 || true)
if [ -n \"\$PID\" ]; then kill \"\$PID\"; sleep 3; fi
LACLAUGPT_VIS_ANALYSIS_DATA_DIR=\$HOME/$REMOTE_DIR/data PYTHONPATH=\$HOME/$REMOTE_DIR/src \
setsid --fork $PYTHON -m streamlit run src/laclaugpt_visualization/ep24_reprocessed_app.py \
  --server.port $PORT --server.address 0.0.0.0 --server.headless true \
  --browser.gatherUsageStats false > /tmp/ep24_demo_$PORT.log 2>&1 < /dev/null
sleep 12
ss -ltn | grep -q ':$PORT ' && echo LISTENING || { echo DOWN; tail -20 /tmp/ep24_demo_$PORT.log; exit 1; }"

echo "== external check"
# `hostname -I` is the host's *internal* address, which is not the address a researcher opens and is
# routinely unreachable from here — it printed a misleading "000" on every deploy. Check the address
# people actually use, and say what a failure means.
# An SSH alias ("SpectacleScraper") is not resolvable by curl, so resolve it through ssh -G first.
PUBLIC_HOST="${PUBLIC_HOST:-$(ssh -G "$HOST" 2>/dev/null | awk '/^hostname /{print $2; exit}')}"
code="$(curl -s -o /dev/null -m 10 -w '%{http_code}' "http://$PUBLIC_HOST:$PORT/" || true)"
if [ "$code" = "200" ]; then
    echo "reachable: http://$PUBLIC_HOST:$PORT/"
else
    echo "NOT reachable from here: http://$PUBLIC_HOST:$PORT/ -> ${code:-timeout}"
    echo "  Service up locally?  ssh $HOST 'ss -ltn | grep :$PORT'"
    echo "  If it listens but is unreachable, port $PORT is closed in the host firewall."
fi
echo "done: inspect /tmp/ep24_demo_$PORT.log on the host for runtime errors"
