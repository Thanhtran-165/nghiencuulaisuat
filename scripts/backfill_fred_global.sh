#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

# Keep DB path consistent with local server / launch agents.
STATE_DIR="${STATE_DIR:-}"
if [[ -z "${STATE_DIR}" ]]; then
  STATE_DIR="${HOME}/Library/Application Support/vn-bond-lab"
fi
mkdir -p "${STATE_DIR}/logs" "${STATE_DIR}/raw" "${STATE_DIR}/pids"

# Use python3.11 if available, else fallback to python3.
PY_BIN="${PY_BIN:-}"
if [[ -z "${PY_BIN}" ]]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PY_BIN="python3.11"
  else
    PY_BIN="python3"
  fi
fi

# Defaults for local DB (same one the server uses by default).
export DB_PATH="${DB_PATH:-${STATE_DIR}/bonds.duckdb}"
export RAW_DATA_PATH="${RAW_DATA_PATH:-${STATE_DIR}/raw}"

LOG_FILE="${LOG_FILE:-${STATE_DIR}/logs/fred_backfill.log}"

END_DATE="${END_DATE:-$(/bin/date +%F)}"
DAYS="${DAYS:-365}"
START_DATE="${START_DATE:-$("$PY_BIN" - <<PY
from datetime import date, timedelta
end = date.fromisoformat("${END_DATE}")
print((end - timedelta(days=int("${DAYS}"))).isoformat())
PY
)}"

# Stop server if running to avoid DuckDB locks.
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"
if curl -fsS "http://${HOST}:${PORT}/healthz" >/dev/null 2>&1; then
  echo "[${END_DATE}] Server detected at http://${HOST}:${PORT} - stopping to avoid DuckDB locks" >>"$LOG_FILE" 2>&1 || true
  ./scripts/stop_local_server.sh || true
  sleep 0.5
fi

{
  echo "[${END_DATE}] Backfilling FRED global series (providers: fred_global)"
  echo "  DB_PATH=$DB_PATH"
  echo "  RAW_DATA_PATH=$RAW_DATA_PATH"
  echo "  Range: $START_DATE -> $END_DATE"
  "$PY_BIN" -m app.ingest backfill --start "$START_DATE" --end "$END_DATE" --providers fred_global
  echo "[${END_DATE}] Done"
} >>"$LOG_FILE" 2>&1

./scripts/run_local_all.sh >/dev/null 2>&1 || true

echo "✓ Backfill complete. Log: $LOG_FILE"
