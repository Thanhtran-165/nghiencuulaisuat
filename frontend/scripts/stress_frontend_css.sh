#!/bin/bash
# Stress test for CSS loading in Next.js dev server
# This script tests CSS availability across multiple routes and iterations
# to catch intermittent CSS loading failures.

set -e

BASE_URL="http://localhost:3001"
ITERATIONS=50
FAIL_COUNT=0

echo "========================================="
echo "CSS Stress Test - Next.js Dev Server"
echo "========================================="
echo "Base URL: $BASE_URL"
echo "Iterations: $ITERATIONS"
echo ""

# Routes to test
ROUTES=("/" "/lich-su" "/so-sanh" "/may-tinh")

# Function to extract CSS URL from HTML
extract_css_url() {
    local html="$1"
    echo "$html" | grep -oE 'href="/_next/static/css/[^"]+' | sed 's/href="//; s/"//g' | head -1
}

# Function to test CSS loading
test_css() {
    local route="$1"
    local iteration="$2"

    # Fetch HTML
    local html=$(curl -s "$BASE_URL$route" 2>&1)

    # Extract CSS URL
    local css_url=$(extract_css_url "$html")

    if [ -z "$css_url" ]; then
        echo "❌ [Iter $iteration] $route - No CSS link found in HTML"
        return 1
    fi

    # Test CSS file HTTP status
    local css_status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL$css_url" 2>&1)

    if [ "$css_status" != "200" ]; then
        echo "❌ [Iter $iteration] $route - CSS returned HTTP $css_status"
        echo "   CSS URL: $BASE_URL$css_url"
        return 1
    fi

    # Test CSS content for theme tokens
    local css_content=$(curl -s "$BASE_URL$css_url" 2>&1)
    local glass_count=$(echo "$css_content" | grep -c "glass-card" || echo "0")
    local tailwind_count=$(echo "$css_content" | grep -c "@tailwind\|\.glass" || echo "0")

    if [ "$glass_count" -eq 0 ] && [ "$tailwind_count" -eq 0 ]; then
        echo "❌ [Iter $iteration] $route - CSS missing theme tokens"
        echo "   CSS URL: $BASE_URL$css_url"
        echo "   glass-card count: $glass_count"
        echo "   tailwind count: $tailwind_count"
        return 1
    fi

    echo "✓ [Iter $iteration] $route - OK (glass: $glass_count, tailwind: $tailwind_count)"
    return 0
}

# Run stress test
echo "Starting stress test..."
echo ""

for i in $(seq 1 $ITERATIONS); do
    echo "--- Iteration $i ---"

    for route in "${ROUTES[@]}"; do
        if ! test_css "$route" "$i"; then
            FAIL_COUNT=$((FAIL_COUNT + 1))
        fi
    done

    # Small delay between iterations
    sleep 0.2
done

echo ""
echo "========================================="
echo "Stress Test Results"
echo "========================================="
echo "Total iterations: $ITERATIONS"
echo "Routes tested: ${#ROUTES[@]}"
echo "Total tests: $((ITERATIONS * ${#ROUTES[@]}))"
echo "Failures: $FAIL_COUNT"
echo ""

if [ $FAIL_COUNT -gt 0 ]; then
    echo "❌ STRESS TEST FAILED"
    echo "CSS loading is unstable!"
    exit 1
else
    echo "✅ STRESS TEST PASSED"
    echo "CSS loading is stable!"
    exit 0
fi
