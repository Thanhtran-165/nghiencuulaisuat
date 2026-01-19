#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export DEMO_MODE=false
export HOST=127.0.0.1
export PORT=8001
export RATE_LIMIT_SECONDS=0.2

# IMPORTANT:
# Backfill must write into the same DuckDB file that the local server uses.
# By default, the server uses `~/Library/Application Support/vn-bond-lab/bonds.duckdb`.
STATE_DIR="${STATE_DIR:-}"
if [[ -z "${STATE_DIR}" ]]; then
  STATE_DIR="${HOME}/Library/Application Support/vn-bond-lab"
fi
mkdir -p "${STATE_DIR}/raw" "${STATE_DIR}/logs" "${STATE_DIR}/pids"
export DB_PATH="${DB_PATH:-${STATE_DIR}/bonds.duckdb}"
export RAW_DATA_PATH="${RAW_DATA_PATH:-${STATE_DIR}/raw}"

# Use python3.11 if available, else fallback to python3.
PY_BIN="${PY_BIN:-}"
if [[ -z "${PY_BIN}" ]]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PY_BIN="python3.11"
  else
    PY_BIN="python3"
  fi
fi

START_YC="${START_YC:-2014-01-01}"
START_AUCTION="${START_AUCTION:-2013-01-01}"
START_TRADING="${START_TRADING:-2025-01-01}"
END_DATE="${END_DATE:-$(date +%F)}"

mkdir -p logs

ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }

echo "[$(ts)] Backfill start (end=${END_DATE})"
echo "[$(ts)] DB_PATH=${DB_PATH}"
echo "[$(ts)] RAW_DATA_PATH=${RAW_DATA_PATH}"

# Stop server if running to avoid DuckDB file lock issues.
if curl -fsS "http://${HOST}:${PORT}/healthz" >/dev/null 2>&1; then
  echo "[$(ts)] Server detected at http://${HOST}:${PORT} - stopping to avoid DuckDB locks"
  ./scripts/stop_local_server.sh || true
  sleep 0.5
fi

echo "[$(ts)] Yield curve: ${START_YC}..${END_DATE} (monthly)"
"$PY_BIN" -m app.ingest backfill-chunked --start "${START_YC}" --end "${END_DATE}" --providers hnx_yield_curve --chunk monthly

echo "[$(ts)] Auctions: ${START_AUCTION}..${END_DATE} (yearly)"
"$PY_BIN" -m app.ingest backfill-chunked --start "${START_AUCTION}" --end "${END_DATE}" --providers hnx_auction --chunk yearly

echo "[$(ts)] Trading: ${START_TRADING}..${END_DATE} (monthly)"
"$PY_BIN" -m app.ingest backfill-chunked --start "${START_TRADING}" --end "${END_DATE}" --providers hnx_trading --chunk monthly

echo "[$(ts)] Backfill finished, starting server + frontend"
./scripts/run_local_all.sh || true
echo "[$(ts)] Done"
