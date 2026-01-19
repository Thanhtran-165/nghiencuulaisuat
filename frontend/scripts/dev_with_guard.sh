#!/bin/bash
# Development server with CSS guardrail verification
# Runs dev server + stress test, fails fast if CSS issues detected

set -e

BASE_URL="http://localhost:3001"
DEV_PORT=3001

echo "========================================="
echo "Dev Server with Guardrail Verification"
echo "========================================="
echo ""

# Stop any existing dev server from this project (safer than killing by port).
echo "🔍 Checking for existing dev server for this project..."
node scripts/kill_project_next_dev.mjs --ignore-missing --quiet || true
sleep 1

# If port is still in use, it's likely another process (not this project).
if lsof -ti:$DEV_PORT > /dev/null 2>&1; then
  echo "❌ Port $DEV_PORT is still in use by another process."
  echo "   Free the port or change the dev port (package.json) and try again."
  exit 1
fi

# Start dev server in background
echo ""
echo "🚀 Starting dev server (with cache check)..."
npm run dev > /tmp/dev_server.log 2>&1 &
DEV_PID=$!

echo "ℹ️  Dev server PID: $DEV_PID"
echo "ℹ️  Log file: /tmp/dev_server.log"
echo ""

# Wait for server to be ready
echo "⏳ Waiting for dev server to be ready..."
MAX_WAIT=30
WAIT_COUNT=0

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
  if curl -s "$BASE_URL" > /dev/null 2>&1; then
    echo "✅ Dev server is ready!"
    echo ""
    break
  fi

  WAIT_COUNT=$((WAIT_COUNT + 1))
  echo "   Waiting... ($WAIT_COUNT/$MAX_WAIT)"
  sleep 1

  # Check if process died
  if ! ps -p $DEV_PID > /dev/null 2>&1; then
    echo "❌ Dev server failed to start!"
    echo ""
    echo "=== Dev Server Log ==="
    cat /tmp/dev_server.log
    echo "======================"
    echo ""
    exit 1
  fi
done

if [ $WAIT_COUNT -eq $MAX_WAIT ]; then
  echo "❌ Timeout waiting for dev server!"
  echo ""
  echo "=== Dev Server Log ==="
  cat /tmp/dev_server.log
  echo "======================"
  echo ""
  kill $DEV_PID 2>/dev/null || true
  exit 1
fi

# Run stress test
echo "========================================="
echo "Running CSS Guardrail Verification"
echo "========================================="
echo ""

bash scripts/stress_frontend_css.sh
TEST_RESULT=$?

echo ""
echo "========================================="
if [ $TEST_RESULT -eq 0 ]; then
  echo "✅ Guardrail verification PASSED"
  echo ""
  echo "🎉 Dev server is running with verified CSS!"
  echo "   URL: $BASE_URL"
  echo "   PID: $DEV_PID"
  echo ""
  echo "Press Ctrl+C to stop the server"
  echo "========================================="
  echo ""

  # Keep dev server running until user stops it
  trap "echo ''; echo '🛑 Stopping dev server...'; kill $DEV_PID 2>/dev/null || true; exit 0" INT TERM

  # Tail the log
  tail -f /tmp/dev_server.log &
  TAIL_PID=$!

  # Wait for dev server
  wait $DEV_PID
  EXIT_CODE=$?

  # Cleanup tail
  kill $TAIL_PID 2>/dev/null || true

  exit $EXIT_CODE
else
  echo "❌ Guardrail verification FAILED"
  echo ""
  echo "⚠️  CSS loading is unstable! Stopping dev server."
  echo "========================================="
  echo ""
  kill $DEV_PID 2>/dev/null || true
  exit 1
fi
