#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

STATE_DIR="${STATE_DIR:-}"
if [[ -z "${STATE_DIR}" ]]; then
  STATE_DIR="${HOME}/Library/Application Support/vn-bond-lab"
fi

mkdir -p "${STATE_DIR}/logs"
mkdir -p "${STATE_DIR}/raw"

# Default providers: all daily-capable official sources.
# Override with:
#   PROVIDERS="sbv_interbank sbv_policy hnx_trading" ./scripts/run_local_ingest.sh
PROVIDERS="${PROVIDERS:-hnx_yield_curve hnx_ftp_pdf hnx_auction hnx_trading sbv_interbank sbv_policy fred_global lai_suat_rates}"

# Use python3.11 if available, else fallback to python3.
PY_BIN="${PY_BIN:-}"
if [[ -z "${PY_BIN}" ]]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PY_BIN="python3.11"
  else
    PY_BIN="python3"
  fi
fi

export DEMO_MODE="${DEMO_MODE:-false}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export DB_PATH="${DB_PATH:-${STATE_DIR}/bonds.duckdb}"
export RAW_DATA_PATH="${RAW_DATA_PATH:-${STATE_DIR}/raw}"

LOG_FILE="${LOG_FILE:-${STATE_DIR}/logs/local_ingest.log}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"

iso_now() {
  # macOS/BSD `date` doesn't support `-I*`, so format manually.
  date "+%Y-%m-%dT%H:%M:%S%z"
}

{
  echo "[$(iso_now)] Starting local ingest"
  echo "[$(iso_now)] ROOT_DIR=$ROOT_DIR"
  echo "[$(iso_now)] PY_BIN=$PY_BIN"
  echo "[$(iso_now)] PROVIDERS=$PROVIDERS"
  # If the server is running, trigger ingest in-process to avoid DuckDB file locks.
  if curl -fsS "http://${HOST}:${PORT}/healthz" >/dev/null 2>&1; then
    echo "[$(iso_now)] Server detected at http://${HOST}:${PORT} - using /api/admin/ingest/daily"
    # Pass providers explicitly so the server-side run matches local defaults.
    qs=""
    for p in $PROVIDERS; do
      if [[ -z "$qs" ]]; then
        qs="providers=$p"
      else
        qs="${qs}&providers=$p"
      fi
    done
    curl -fsS -X POST "http://${HOST}:${PORT}/api/admin/ingest/daily?${qs}" >/dev/null
  else
    "$PY_BIN" -m app.ingest daily --providers $PROVIDERS
  fi
  echo "[$(iso_now)] Done"
} >>"$LOG_FILE" 2>&1
