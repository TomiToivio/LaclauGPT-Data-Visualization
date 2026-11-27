#!/usr/bin/env bash
# Install or update one public AI26 demo release from a verified bundle (issue #342).
#
# The demo copy is a versioned directory tree plus a `current` symlink:
#
#   /srv/ai26-demo/releases/<stamp>/records.jsonl
#   /srv/ai26-demo/releases/<stamp>/graph.json      (optional)
#   /srv/ai26-demo/releases/<stamp>/manifest.json
#   /srv/ai26-demo/current -> releases/<stamp>
#
# A switch is only committed after every checksum in the manifest matches and the service answers
# its health endpoint. A failed update puts the previous release back, so a broken bundle never
# leaves the public copy serving half a dataset or a stale one silently.
set -euo pipefail

usage() {
  cat <<'EOF'
usage: update_ai26_demo_release.sh --bundle DIR --root DIR [options]

  --bundle DIR       directory holding manifest.json (+ records.jsonl, optional graph.json)
  --root DIR         demo root that keeps releases/ and current/ (e.g. /srv/ai26-demo)
  --service NAME     systemd unit to restart (default: ai26-demo.service)
  --health-url URL   readiness endpoint (default: http://127.0.0.1:8600/_stcore/health)
  --stamp VALUE      release directory name (default: manifest generated_at, sanitised)
  --dry-run          verify and print the plan; touch nothing
  -h, --help         this message
EOF
}

BUNDLE="" ROOT="" SERVICE="ai26-demo.service" HEALTH_URL="http://127.0.0.1:8600/_stcore/health" STAMP="" DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle) BUNDLE=${2:?}; shift 2 ;;
    --root) ROOT=${2:?}; shift 2 ;;
    --service) SERVICE=${2:?}; shift 2 ;;
    --health-url) HEALTH_URL=${2:?}; shift 2 ;;
    --stamp) STAMP=${2:?}; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ -n "$BUNDLE" && -n "$ROOT" ]] || { usage >&2; exit 2; }
[[ -f "$BUNDLE/manifest.json" ]] || { echo "no manifest.json in $BUNDLE" >&2; exit 2; }
command -v python3 >/dev/null || { echo "python3 is required to read the manifest" >&2; exit 2; }

# The manifest is the contract: file list, per-file sha256, record count, data-as-of, code revision.
read -r STAMP_DEFAULT FILES <<<"$(python3 - "$BUNDLE/manifest.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
stamp = str(m.get("data_as_of") or m.get("generated_at") or "release")
safe = "".join(c if c.isalnum() or c in "-._" else "-" for c in stamp)[:60] or "release"
files = " ".join(sorted((m.get("files") or {}).keys()))
print(safe, files)
PY
)"
STAMP=${STAMP:-$STAMP_DEFAULT}

echo "bundle:   $BUNDLE"
echo "root:     $ROOT"
echo "release:  $STAMP"
echo "files:    $FILES"

# 1. Verify before writing anything.
python3 - "$BUNDLE" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
files = manifest.get("files") or {}
if not files:
    raise SystemExit("manifest lists no files")
for name, expected in files.items():
    path = root / name
    if not path.is_file():
        raise SystemExit(f"missing bundle file: {name}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise SystemExit(f"checksum mismatch for {name}: {digest[:12]} != {expected[:12]}")
print(f"verified {len(files)} file(s), {manifest.get('records', '?')} record(s), "
      f"data_as_of={manifest.get('data_as_of', '?')}, code_revision={manifest.get('code_revision', '?')}")
PY

TARGET="$ROOT/releases/$STAMP"
CURRENT="$ROOT/current"
if [[ "$DRY_RUN" == "1" ]]; then
  echo "dry run: would write $TARGET, point $CURRENT at it, restart $SERVICE, check $HEALTH_URL"
  exit 0
fi

PREVIOUS=""
if [[ -L "$CURRENT" ]]; then PREVIOUS=$(readlink -f "$CURRENT"); fi

# 2. Stage the release beside the live one; never write into `current`.
mkdir -p "$ROOT/releases"
rm -rf "$TARGET"
mkdir -p "$TARGET"
for name in $FILES; do cp "$BUNDLE/$name" "$TARGET/$name"; done
cp "$BUNDLE/manifest.json" "$TARGET/manifest.json"

# 3. Switch atomically and prove the service is healthy afterwards.
ln -sfn "$TARGET" "$CURRENT.tmp"
mv -Tf "$CURRENT.tmp" "$CURRENT"

restart() { systemctl restart "$SERVICE" 2>/dev/null || systemctl --user restart "$SERVICE"; }
healthy() {
  for _ in $(seq 1 30); do
    if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  return 1
}

restart
if healthy; then
  echo "updated: $CURRENT -> $TARGET"
  exit 0
fi

echo "health check failed after switching to $STAMP" >&2
if [[ -n "$PREVIOUS" && -d "$PREVIOUS" ]]; then
  ln -sfn "$PREVIOUS" "$CURRENT.tmp"
  mv -Tf "$CURRENT.tmp" "$CURRENT"
  restart || true
  echo "rolled back to $PREVIOUS" >&2
else
  echo "no previous release to roll back to" >&2
fi
exit 1
