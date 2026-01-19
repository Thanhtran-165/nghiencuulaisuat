#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

PORT="${PORT:-8001}"
DAYS="${DAYS:-365}"

echo "Refreshing global (FRED) data and restarting server..."
PORT="$PORT" ./scripts/stop_local_server.sh || true

# Backfill global data into the same DB the server uses by default.
DAYS="$DAYS" ./scripts/backfill_fred_global.sh

PORT="$PORT" ./scripts/run_local_server.sh

