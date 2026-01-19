#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"

echo "Stopping Next.js frontend..."
./scripts/stop_local_frontend.sh || true

echo "Stopping VN Bond Lab server..."
./scripts/stop_local_server.sh

echo "✓ All stopped"
