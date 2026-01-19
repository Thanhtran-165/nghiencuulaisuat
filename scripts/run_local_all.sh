#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"

echo "Starting VN Bond Lab server..."
./scripts/run_local_server.sh

echo "Waiting for API to be ready..."
for _ in {1..50}; do
  if curl -fsS "http://${HOST}:${PORT}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

echo "Starting Next.js frontend (VN Bond Lab UI) on port 3002..."
./scripts/run_local_frontend.sh || true

echo "Syncing Lai_suat rates into DuckDB (missing range)..."
curl -fsS -X POST "http://${HOST}:${PORT}/api/admin/lai-suat/sync-missing" >/dev/null || true

echo "✓ All started"
echo "  Bond Lab:   http://${HOST}:${PORT}"
echo "  Frontend:   http://127.0.0.1:3002"
