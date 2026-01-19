#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

PORT="${PORT:-8001}"
STATE_DIR="${STATE_DIR:-}"
if [[ -z "${STATE_DIR}" ]]; then
  STATE_DIR="${HOME}/Library/Application Support/vn-bond-lab"
fi
PID_FILE="${PID_FILE:-${STATE_DIR}/pids/uvicorn_${PORT}.pid}"

stop_pid() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    return 0
  fi
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi
  kill "$pid" >/dev/null 2>&1 || true
  for _ in {1..20}; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done
  kill -9 "$pid" >/dev/null 2>&1 || true
}

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" || true)"
  stop_pid "$PID"
  rm -f "$PID_FILE"
  echo "✓ Stopped server (pid ${PID:-unknown})"
  exit 0
fi

# Fallback: try to find process by port.
PIDS="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)"
if [[ -n "$PIDS" ]]; then
  for pid in $PIDS; do
    stop_pid "$pid"
  done
  echo "✓ Stopped server on port $PORT"
  exit 0
fi

echo "No server found to stop on port $PORT"
