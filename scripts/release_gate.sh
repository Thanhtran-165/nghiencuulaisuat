#!/bin/bash
# Release Gate Script - One-command RC validation
#
# This script:
# 1. Starts production stack
# 2. Runs smoke tests
# 3. Captures PASS/FAIL evidence to disk for audit
#
# Usage:
#   chmod +x scripts/release_gate.sh
#   bash scripts/release_gate.sh
#
# Optional overrides:
#   READY_TIMEOUT=300 LOG_TAIL=5000 bash scripts/release_gate.sh
#   LOG_SINCE="24h" bash scripts/release_gate.sh

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Configuration
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
READY_TIMEOUT="${READY_TIMEOUT:-120}"  # Max seconds to wait for readiness
LOG_TAIL="${LOG_TAIL:-2000}"           # Number of log lines to capture
LOG_SINCE="${LOG_SINCE:-}"              # Optional: --since flag (e.g., "24h", "1h")
EVIDENCE_BASE_DIR="data/release_evidence"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create evidence directory
mkdir -p "$EVIDENCE_BASE_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
EVIDENCE_DIR="$EVIDENCE_BASE_DIR/rc_${TIMESTAMP}"
mkdir -p "$EVIDENCE_DIR"

log_info "Release Gate - RC Validation"
log_info "Evidence directory: $EVIDENCE_DIR"
echo

# Step 1: Start production stack
log_info "Step 1: Starting production stack..."
docker compose -f "$COMPOSE_FILE" up -d --build

# Step 2: Wait for readiness
log_info "Step 2: Waiting for application readiness (max ${READY_TIMEOUT}s)..."
for i in $(seq 1 $READY_TIMEOUT); do
    if curl -s "${BASE_URL}/readyz" | grep -q '"status":"ready"' 2>/dev/null; then
        log_info "Application is ready after ${i}s"
        break
    fi

    if [ $i -eq $READY_TIMEOUT ]; then
        log_error "Timeout waiting for readiness"
        echo "FAIL: Application did not become ready within ${READY_TIMEOUT}s" | tee "${EVIDENCE_DIR}/RESULT.txt"
        echo "FAIL" > "${EVIDENCE_DIR}/STATUS.txt"
        docker compose -f "$COMPOSE_FILE" logs --no-log-prefix > "${EVIDENCE_DIR}/docker_logs.txt" 2>&1
        log_error "FAIL evidence saved to: $EVIDENCE_DIR"
        exit 1
    fi

    sleep 1
done

echo

# Step 3: Run smoke tests
log_info "Step 3: Running smoke tests..."
if bash scripts/rc_smoke.sh 2>&1 | tee "${EVIDENCE_DIR}/rc_smoke.log"; then
    SMOKE_RESULT="PASS"
    log_info "Smoke tests: PASS"
else
    SMOKE_RESULT="FAIL"
    log_error "Smoke tests: FAIL"
fi
echo

# Step 4: Collect artifacts
log_info "Step 4: Collecting evidence artifacts..."

# Readiness check
curl -s "${BASE_URL}/readyz" | tee "${EVIDENCE_DIR}/readyz.json" >/dev/null
log_info "  ✓ readyz.json"

# Version info
curl -s "${BASE_URL}/api/version" | jq . | tee "${EVIDENCE_DIR}/version.json" >/dev/null
log_info "  ✓ version.json"

# Snapshot page
curl -s "${BASE_URL}/snapshot/today" > "${EVIDENCE_DIR}/snapshot.html"
log_info "  ✓ snapshot.html"

# Daily PDF
curl -s "${BASE_URL}/report/daily.pdf" -o "${EVIDENCE_DIR}/daily.pdf"
PDF_SIZE=$(stat -f%z "${EVIDENCE_DIR}/daily.pdf" 2>/dev/null || stat -c%s "${EVIDENCE_DIR}/daily.pdf" 2>/dev/null || echo "0")
if [ "$PDF_SIZE" -gt 0 ]; then
    log_info "  ✓ daily.pdf (${PDF_SIZE} bytes)"
else
    log_warn "  ✗ daily.pdf (empty or failed)"
fi

# Docker logs
LOG_CAPTURE_INFO="last ${LOG_TAIL} lines"
if [ -n "$LOG_SINCE" ]; then
    docker compose -f "$COMPOSE_FILE" logs --no-log-prefix --tail "${LOG_TAIL}" --since "${LOG_SINCE}" > "${EVIDENCE_DIR}/docker_logs.txt" 2>&1
    LOG_CAPTURE_INFO="last ${LOG_TAIL} lines (since ${LOG_SINCE})"
else
    docker compose -f "$COMPOSE_FILE" logs --no-log-prefix --tail "${LOG_TAIL}" > "${EVIDENCE_DIR}/docker_logs.txt" 2>&1
    LOG_CAPTURE_INFO="last ${LOG_TAIL} lines"
fi
log_info "  ✓ docker_logs.txt (${LOG_CAPTURE_INFO})"

echo

# Step 5: Generate summary
log_info "Step 5: Generating summary..."

{
    echo "Release Gate Evidence Summary"
    echo "============================="
    echo "Timestamp: $TIMESTAMP"
    echo "Evidence Directory: $EVIDENCE_DIR"
    echo
    echo "Configuration:"
    echo "  READY_TIMEOUT: ${READY_TIMEOUT}s"
    echo "  LOG_CAPTURE: ${LOG_CAPTURE_INFO}"
    echo
    echo "Smoke Test Result: $SMOKE_RESULT"
    echo
    echo "Artifacts:"
    echo "  - rc_smoke.log (smoke test output)"
    echo "  - readyz.json (readiness check)"
    echo "  - version.json (version info)"
    echo "  - snapshot.html (daily snapshot)"
    echo "  - daily.pdf (daily report)"
    echo "  - docker_logs.txt (container logs - ${LOG_CAPTURE_INFO})"
    echo
    echo "Result: $SMOKE_RESULT"
} | tee "${EVIDENCE_DIR}/SUMMARY.txt"

echo
echo "========================================"

# Final result
if [ "$SMOKE_RESULT" = "PASS" ]; then
    log_info "✓ PASS - Evidence saved to: $EVIDENCE_DIR"
    echo "PASS" > "${EVIDENCE_DIR}/STATUS.txt"
    echo
    echo "Release Candidate is ready for deployment!"
    echo "Next step: See docs/RUNBOOK_SMOKE.md 'Release Tagging (RC)' section"
    exit 0
else
    log_error "✗ FAIL - Evidence saved to: $EVIDENCE_DIR"
    echo "FAIL" > "${EVIDENCE_DIR}/STATUS.txt"
    echo
    echo "Review failures in: ${EVIDENCE_DIR}/rc_smoke.log"
    echo "See docs/RUNBOOK_SMOKE.md 'Troubleshooting Decision Tree' section"
    exit 1
fi
