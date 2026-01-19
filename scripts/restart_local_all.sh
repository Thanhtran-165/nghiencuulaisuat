#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-3002}"

DOMAIN="gui/$(id -u)"

kickstart_if_exists() {
  local label="$1"
  if launchctl print "${DOMAIN}/${label}" >/dev/null 2>&1; then
    launchctl kickstart -k "${DOMAIN}/${label}" >/dev/null 2>&1 || true
    return 0
  fi
  return 1
}

echo "Restarting VN Bond Lab (preferred: launchd)…"

USED_LAUNCHD=0
if kickstart_if_exists "com.vn-bond-lab.server"; then
  USED_LAUNCHD=1
fi
if kickstart_if_exists "com.vn-bond-lab.frontend"; then
  USED_LAUNCHD=1
fi

if [[ "$USED_LAUNCHD" -eq 0 ]]; then
  echo "launchd jobs not found; falling back to local scripts…"
  ./scripts/stop_local_all.sh || true
  ./scripts/run_local_all.sh
else
  echo "Waiting for API to be ready…"
  for _ in {1..80}; do
    if curl -fsS "http://${HOST}:${PORT}/healthz" >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done
fi

echo "✓ Ready"
echo "  Backend:  http://${HOST}:${PORT}"
echo "  Frontend: http://127.0.0.1:${FRONTEND_PORT}"

