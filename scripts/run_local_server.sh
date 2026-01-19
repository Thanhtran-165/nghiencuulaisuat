#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

# Use python3.11 if available, else fallback to python3.
PY_BIN="${PY_BIN:-}"
if [[ -z "${PY_BIN}" ]]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PY_BIN="python3.11"
  else
    PY_BIN="python3"
  fi
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"

STATE_DIR="${STATE_DIR:-}"
if [[ -z "${STATE_DIR}" ]]; then
  STATE_DIR="${HOME}/Library/Application Support/vn-bond-lab"
fi

mkdir -p "${STATE_DIR}/raw" "${STATE_DIR}/logs" "${STATE_DIR}/pids"

# IMPORTANT:
# Keep DB path consistent with `scripts/run_local_ingest.sh` so data you ingest
# appears immediately in the running UI.
export DB_PATH="${DB_PATH:-${STATE_DIR}/bonds.duckdb}"
export RAW_DATA_PATH="${RAW_DATA_PATH:-${STATE_DIR}/raw}"

LOG_FILE="${LOG_FILE:-${STATE_DIR}/logs/uvicorn_${PORT}.log}"
PID_FILE="${PID_FILE:-${STATE_DIR}/pids/uvicorn_${PORT}.pid}"

if [[ -f "$PID_FILE" ]]; then
  if kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
    echo "Server already running (pid $(cat "$PID_FILE"))"
    exit 0
  fi
fi

nohup "$PY_BIN" -m uvicorn app.main:app --host "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

echo "✓ Started server: http://${HOST}:${PORT}"
echo "  PID: $(cat "$PID_FILE")"
echo "  Log: $LOG_FILE"
echo "  DB:  ${DB_PATH}"
