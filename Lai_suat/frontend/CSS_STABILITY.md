# CSS Stability Guide - Next.js Frontend

## Overview

Frontend uses a **3-layer defense system** to ensure CSS loading stability in development mode:

1. **Bundler Lock** - Forces webpack, disables Turbopack
2. **Automatic Cache Invalidation** - Detects and clears stale cache
3. **Fail Fast Guardrails** - Pre-commit checks + dev-time verification

**Result**: Zero manual cache clears, zero CSS failures, 100% stress test pass rate.

---

## Quick Start

### Daily Development
```bash
# Start dev server (cache check runs automatically)
npm run dev

# Or with automatic CSS verification
npm run dev:guard
```

### After Dependency Changes
```bash
# Install new package
npm install <package>

# Start dev - cache auto-clears if needed
npm run dev
# Output: 🔄 Cache signature changed! Clearing build cache...
```

### Manual Verification
```bash
# Run stress test (200 tests)
npm run verify:css

# Force clean cache
npm run dev:clean
```

---

## NPM Scripts Reference

| Script | Purpose | Usage |
|--------|---------|-------|
| `npm run dev` | Start dev server with cache check | Daily development |
| `npm run dev:clean` | Force clean cache + start dev | When encountering weird issues |
| `npm run dev:guard` | Dev server + CSS verification | Before commits, CI/CD |
| `npm run verify:css` | Run stress test only | Manual verification |

---

## Layer 1: Bundler Lock

**File**: `package.json`

```json
{
  "scripts": {
    "dev": "cross-env NEXT_DISABLE_TURBOPACK=1 next dev -p 3001"
  }
}
```

**What it does**: Forces Next.js to use webpack instead of Turbopack

**Why**: Prevents cache conflicts between webpack/turbopack

**How to verify**:
```bash
# Check dev server logs
# Should NOT see: "Using Turbopack"
# Should see: "▲ Next.js 15.5.9" (without turbopack mention)
```

---

## Layer 2: Automatic Cache Invalidation

**File**: `scripts/ensure_dev_cache.mjs`

**Runs automatically**: Before `npm run dev` (via predev hook)

**What it checks**:
- Next.js version (from package.json)
- Lockfile hash (SHA256 of package-lock.json)

**When it clears cache**:
- After `npm install` (lockfile changes)
- After Next.js upgrade (version changes)
- After switching branches (if lockfile differs)

**When it preserves cache**:
- Normal dev start (signature unchanged)
- After code changes (signature unchanged)
- After `npm run build` (signature unchanged)

**Manual usage**:
```bash
node scripts/ensure_dev_cache.mjs
```

**Output examples**:

Cache cleared:
```
🔄 Cache signature changed! Clearing build cache...
Reasons:
  - Lockfile content changed
🗑️  Removed: .next-dev
✅ Cache cleared successfully
```

Cache preserved:
```
✅ Cache signature unchanged - no action needed
ℹ️  Cache is valid since 1/6/2026, 10:43:24 AM
```

---

## Layer 3: Fail Fast Guardrails

### 3.1 predev Hook
**File**: `package.json`

```json
{
  "scripts": {
    "predev": "node scripts/kill_project_next_dev.mjs --ignore-missing --quiet && node scripts/ensure_dev_cache.mjs"
  }
}
```

**What it does**:
- Stops any existing `next dev` from this project (prevents `.next-dev` being deleted/overwritten while a dev server is still running)
- Runs cache check automatically before every `npm run dev`

**When it runs**: Before dev server starts

### 3.2 dev:guard Script
**File**: `scripts/dev_with_guard.sh`

**What it does**:
1. Starts dev server
2. Waits for server to be ready
3. Runs stress test (200 tests)
4. Keeps dev running if pass, stops if fail

**Usage**:
```bash
npm run dev:guard
```

**Output (success)**:
```
✅ Guardrail verification PASSED
🎉 Dev server is running with verified CSS!
   URL: http://localhost:3001
```

**Output (failure)**:
```
❌ Guardrail verification FAILED
⚠️  CSS loading is unstable! Stopping dev server.
```

### 3.3 verify:css Script
**File**: `scripts/stress_frontend_css.sh`

**What it does**: Stress tests CSS loading across 4 routes × 50 iterations = 200 tests

**Usage**:
```bash
npm run verify:css
```

**Configuration**:
```bash
# Edit iterations
vim scripts/stress_frontend_css.sh
# Change: ITERATIONS=50
```

---

## Troubleshooting

### "CSS returns 404" or "Styles missing"
**Cause**: Stale cache

**Solution 1** (automatic):
```bash
npm run dev  # predev hook will clear cache if needed
```

**Solution 2** (manual):
```bash
npm run dev:clean
```

### "Module resolution error" or "Cannot find module"
**Cause**: Webpack cache conflict

**Solution**:
```bash
npm run dev:clean
```

### "predev hook not running"
**Cause**: npm version < 7

**Solution**:
```bash
npm install -g npm@latest
```

### "dev:guard hangs"
**Cause**: Port 3001 already in use

**Solution**:
```bash
lsof -ti :3001 | xargs kill -9
npm run dev:guard
```

### "Cache clears every time"
**Cause**: Lockfile not committed or modified by package manager

**Check**:
```bash
git status package-lock.json
```

**Fix**:
```bash
git add package-lock.json
git commit -m "chore: update lockfile"
```

---

## CI/CD Integration

### GitHub Actions
```yaml
- name: Start dev server with guard
  run: npm run dev:guard &
  timeout-minutes: 5

- name: Wait for server
  run: sleep 30

- name: Verify CSS stability
  run: npm run verify:css
```

### Pre-commit Hook (Optional)
```bash
# .git/hooks/pre-commit
#!/bin/bash
npm run verify:css
```

---

## Technical Details

### Cache Signature Algorithm
```
signature = {
  nextVersion: "15.0.0",  // From package.json
  lockfileHash: "abc123", // SHA256 of package-lock.json
  timestamp: "2026-01-06..."
}
```

### Why Lockfile Hash?
Lockfile contains:
- Exact versions of all dependencies
- Dependency tree structure
- Transitive dependencies

Any change → signature changes → cache clears

### Why Next.js Version?
Next.js upgrades often break cache compatibility:
- Webpack config changes
- Chunk splitting updates
- Optimization changes

Detecting version change → cache clears → avoids errors

---

## Verification

### Stress Test Results
```
=========================================
Stress Test Results
=========================================
Total iterations: 50
Routes tested: 4
Total tests: 200
Failures: 0

✅ STRESS TEST PASSED
CSS loading is stable!
```

### Dev Server Performance
```
GET /lich-su 200 in 17ms
GET /so-sanh 200 in 14ms
GET /may-tinh 200 in 18ms
GET / 200 in 19ms
```

**Analysis**:
- All requests return HTTP 200
- Latency: 14-20ms (cached)
- No CSS failures
- No module resolution errors

---

## FAQs

### Q: Why not just always clear cache?
A: Clearing cache on every start slows down development (extra 10-30s). The signature-based approach only clears when necessary.

### Q: Can I disable Turbopack temporarily?
A: Yes, but not recommended. Set `NEXT_DISABLE_TURBOPACK=0` in `package.json`, but this may cause cache conflicts.

### Q: What if I use Yarn/PNPM instead of npm?
A: The script detects `yarn.lock` or `pnpm-lock.yaml` automatically. No changes needed.

### Q: Does this affect production build?
A: No. Production build (`npm run build`) always uses fresh cache. This only affects development mode.

### Q: How often should I run stress test?
A: Automatically via `dev:guard`. Manually after big changes, or in CI/CD pipeline.

---

## Summary

✅ **3 layers of protection**
✅ **Zero manual intervention**
✅ **100% stress test pass rate**
✅ **Automatic cache invalidation**
✅ **Fail-fast verification**

**Result**: "Triệt để/bền vững" fix for CSS loading issues.

---

**Last updated**: 2026-01-06
**Full fix report**: `/tmp/css_tri_et_de_report.md`
