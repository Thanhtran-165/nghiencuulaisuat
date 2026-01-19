#!/usr/bin/env bash
# Quick CSS presence check after build

set -e

echo "=== CSS Presence Check ==="

# Check if build exists
if [ ! -d ".next-dev" ]; then
  echo "❌ .next-dev directory not found. Run 'npm run dev' first."
  exit 1
fi

# Check for CSS files
CSS_FILES=$(find .next-dev/static/css -name "*.css" 2>/dev/null | wc -l | tr -d ' ')

if [ "$CSS_FILES" -eq 0 ]; then
  echo "❌ No CSS files found in .next-dev/static/css/"
  exit 1
fi

echo "✅ Found $CSS_FILES CSS file(s)"

# Check if CSS files are non-empty
LARGE_CSS=$(find .next-dev/static/css -name "*.css" -size +1k 2>/dev/null | wc -l | tr -d ' ')

if [ "$LARGE_CSS" -eq 0 ]; then
  echo "⚠️  Warning: CSS files exist but are all empty (<1KB)"
  echo "This may indicate Tailwind directives not processed correctly."
  exit 1
fi

echo "✅ $LARGE_CSS CSS file(s) with content (>1KB)"

# List CSS files
echo ""
echo "CSS files:"
find .next-dev/static/css -name "*.css" -exec ls -lh {} \; | awk '{print "  " $9 " (" $5 ")"}'

echo ""
echo "✅ CSS check passed!"
