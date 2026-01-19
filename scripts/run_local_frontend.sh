#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

FRONTEND_DIR="${FRONTEND_DIR:-$ROOT_DIR/frontend}"
PORT="${FRONTEND_PORT:-3002}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8001}"

STATE_DIR="${STATE_DIR:-}"
if [[ -z "${STATE_DIR}" ]]; then
  STATE_DIR="${HOME}/Library/Application Support/vn-bond-lab"
fi

PID_FILE="${PID_FILE:-${STATE_DIR}/pids/next_${PORT}.pid}"
LOG_FILE="${LOG_FILE:-${STATE_DIR}/logs/next_${PORT}.log}"

mkdir -p "${STATE_DIR}/logs" "${STATE_DIR}/pids"

if [[ ! -d "$FRONTEND_DIR" ]]; then
  echo "Frontend directory not found: $FRONTEND_DIR"
  exit 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use. Stop the process or change FRONTEND_PORT."
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN || true
  exit 1
fi

cd "$FRONTEND_DIR"

if [[ ! -d node_modules ]]; then
  echo "Installing frontend dependencies..."
  npm install
fi

# Stop any existing `next dev` for this project (guardrail script)
node scripts/kill_project_next_dev.mjs --ignore-missing --quiet || true

nohup env NEXT_DISABLE_TURBOPACK=1 BACKEND_URL="$BACKEND_URL" npx next dev -p "$PORT" >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

echo "✓ Started frontend: http://127.0.0.1:${PORT}"
echo "  PID: $(cat "$PID_FILE")"
echo "  Log: $LOG_FILE"
