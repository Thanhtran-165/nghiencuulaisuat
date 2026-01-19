#!/bin/bash
# RC Smoke Test Script
# Automated validation for Release Candidate
# Usage: bash scripts/rc_smoke.sh

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
MAX_WAIT="${MAX_WAIT:-60}"  # Maximum seconds to wait for readiness
ADMIN_USER="${ADMIN_USER:-}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"

# Test counters
PASS=0
FAIL=0
WARN=0

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARN++))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAIL++))
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASS++))
}

check_admin_auth() {
    if [ -n "$ADMIN_USER" ] && [ -n "$ADMIN_PASSWORD" ]; then
        echo "true"
    else
        echo "false"
    fi
}

test_endpoint() {
    local name="$1"
    local endpoint="$2"
    local expected_code="${3:-200}"
    local auth="$4"

    echo -n "Testing $name... "

    if [ "$auth" == "true" ]; then
        response=$(curl -s -w "\n%{http_code}" -u "${ADMIN_USER}:${ADMIN_PASSWORD}" "${BASE_URL}${endpoint}")
    else
        response=$(curl -s -w "\n%{http_code}" "${BASE_URL}${endpoint}")
    fi

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n -1)

    if [ "$http_code" == "$expected_code" ]; then
        log_pass "$name (HTTP $http_code)"
        echo "$body" | head -c 200  # Show first 200 chars
        echo "..."
        return 0
    else
        log_error "$name (HTTP $http_code, expected $expected_code)"
        echo "$body"
        return 1
    fi
}

wait_for_readyz() {
    log_info "Waiting for application to be ready (max ${MAX_WAIT}s)..."

    for i in $(seq 1 $MAX_WAIT); do
        if curl -s "${BASE_URL}/readyz" | grep -q '"status":"ok"'; then
            log_pass "Application is ready after ${i}s"
            return 0
        fi
        sleep 1
    done

    log_error "Application not ready after ${MAX_WAIT}s"
    return 1
}

# Main script
main() {
    echo "=========================================="
    echo "  RC Smoke Test - Automated Validation"
    echo "  Version: 1.0.0-rc1"
    echo "  Base URL: $BASE_URL"
    echo "=========================================="
    echo ""

    # Check if docker compose is running
    log_info "Checking Docker Compose status..."
    if docker compose -f "$COMPOSE_FILE" ps | grep -q "Up"; then
        log_pass "Docker Compose is running"
    else
        log_error "Docker Compose is not running"
        log_info "Start it with: docker compose -f $COMPOSE_FILE up -d --build"
        exit 1
    fi

    echo ""

    # Wait for readiness
    if ! wait_for_readyz; then
        echo ""
        echo "=========================================="
        log_error "SMOKE TEST FAILED"
        echo "=========================================="
        exit 1
    fi

    echo ""

    # Test health endpoints
    log_info "Testing Health Endpoints..."
    test_endpoint "Health Check" "/healthz" "200"
    test_endpoint "Readiness Check" "/readyz" "200"
    test_endpoint "Version Info" "/api/version" "200"
    test_endpoint "Metrics" "/metrics" "200"

    echo ""

    # Test key pages
    log_info "Testing Key Pages..."
    test_endpoint "Dashboard" "/" "200"
    test_endpoint "Yield Curve" "/yield-curve" "200"
    test_endpoint "Interbank" "/interbank" "200"
    test_endpoint "Transmission" "/transmission" "200"
    test_endpoint "Stress Model" "/stress" "200"
    test_endpoint "Daily Snapshot" "/snapshot/today" "200"

    echo ""

    # Test PDF report
    log_info "Testing PDF Report..."
    echo -n "Downloading PDF... "
    pdf_response=$(curl -s -w "\n%{http_code}" -o /tmp/rc_smoke_daily.pdf "${BASE_URL}/report/daily.pdf")
    pdf_code=$(echo "$pdf_response" | tail -n1)

    if [ "$pdf_code" == "200" ]; then
        pdf_size=$(wc -c </tmp/rc_smoke_daily.pdf 2>/dev/null || echo "0")
        if [ "$pdf_size" -gt 0 ]; then
            log_pass "PDF downloaded (${pdf_size} bytes)"
            rm -f /tmp/rc_smoke_daily.pdf
        else
            log_error "PDF is empty (0 bytes)"
        fi
    else
        log_error "PDF download failed (HTTP $pdf_code)"
    fi

    echo ""

    # Test admin endpoints (if auth enabled)
    HAS_AUTH=$(check_admin_auth)
    if [ "$HAS_AUTH" == "true" ]; then
        log_info "Testing Admin Endpoints (with auth)..."
        test_endpoint "Monitoring Summary" "/api/admin/monitoring/summary" "200" "true"
        test_endpoint "Monitoring Providers" "/api/admin/monitoring/providers" "200" "true"
        test_endpoint "Monitoring Drift" "/api/admin/monitoring/drift" "200" "true"
        test_endpoint "Quality Dashboard" "/admin/quality" "200" "true"
        test_endpoint "Alerts" "/alerts" "200" "true"
    else
        log_info "ADMIN_AUTH not enabled, skipping admin auth tests"
        log_info "Testing Admin Endpoints (without auth)..."
        test_endpoint "Monitoring Summary" "/api/admin/monitoring/summary" "200"
        test_endpoint "Quality Dashboard" "/admin/quality" "200"
    fi

    echo ""

    # Summary
    echo "=========================================="
    echo "  SMOKE TEST SUMMARY"
    echo "=========================================="
    log_pass "Passed: $PASS"

    if [ $WARN -gt 0 ]; then
        log_warn "Warnings: $WARN"
    fi

    if [ $FAIL -gt 0 ]; then
        log_error "Failed: $FAIL"
        echo ""
        echo "=========================================="
        log_error "OVERALL: FAILED"
        echo "=========================================="
        exit 1
    else
        echo ""
        echo "=========================================="
        log_pass "OVERALL: PASSED"
        echo "=========================================="
        exit 0
    fi
}

# Run main function
main "$@"
