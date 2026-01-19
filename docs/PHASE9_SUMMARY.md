# Phase 9 Implementation Summary: Release Candidate + Smoke Runbook + Demo Data Pack

## Overview

Phase 9 successfully produced a production-ready Release Candidate (RC1), comprehensive operator runbooks for smoke testing, and a demo data pack for instant demonstrations without live scraping.

**Completion Date**: 2026-01-13
**Version**: 1.0.0-rc1
**Status**: ✅ COMPLETE

---

## Files Changed (Diff Summary)

### New Files Created (6 files)

1. **CHANGELOG.md** (new file)
   - Comprehensive changelog by phase
   - Breaking changes: None
   - Documented all features from Phase 2-9

2. **docs/RUNBOOK_SMOKE.md** (new file, ~500 lines)
   - Copy-paste smoke test procedures
   - Build & start (dev + prod)
   - Endpoint verification steps
   - Key page verification
   - Admin endpoint verification
   - Backup & verify procedures
   - Common failures & fixes with solutions

3. **docs/UPGRADE.md** (new file, ~400 lines)
   - Pre-upgrade checklist
   - Upgrade procedure (Git + Manual)
   - Post-upgrade verification
   - Rollback procedure
   - Emergency recovery procedures
   - Zero-downtime upgrade strategies

4. **app/ops/__main__.py** (modified, +230 lines)
   - Added `seed-demo` CLI command
   - Generates synthetic data for N days
   - Seeds all tables with realistic demo data
   - Includes DQ WARN examples and alerts

5. **tests/test_observability.py** (modified, +170 lines)
   - Added `TestDemoMode` class (5 tests)
   - Tests for seed-demo CLI
   - Tests for demo mode endpoints
   - Tests for data provenance

### Modified Files (4 files)

1. **app/version.py** (~30 lines changed)
   - Bumped version to `1.0.0-rc1`
   - Added dynamic `__build_date__`
   - Updated `get_version_info()` to use settings
   - Added `demo_mode_enabled` feature flag

2. **app/config.py** (+2 lines)
   - Added `demo_mode: bool = False` field

3. **.env.example** (+4 lines)
   - Added `DEMO_MODE=false` configuration
   - Documented demo mode behavior

4. **app/templates/base.html** (+30 lines)
   - Added demo mode banner CSS
   - Added conditional demo banner HTML
   - Banner shows "⚠️ DEMO MODE - Showing synthetic demonstration data"

5. **app/main.py** (+15 lines)
   - Added `get_template_context()` helper
   - Updated dashboard to use demo mode context
   - Passes `demo_mode` flag to templates

**Total**: 10 files modified/created, ~1,400 lines added/changed

---

## Deliverables Summary

### 1. RC Version String + Changelog Excerpt

**RC Version**: `1.0.0-rc1`

**Build Date**: Dynamic (set at build time via `datetime.utcnow().isoformat()`)

**Feature Flags**:
```json
{
  "admin_auth_enabled": false,
  "scheduler_enabled": false,
  "global_data_enabled": false,
  "demo_mode_enabled": false
}
```

**Changelog Excerpt** (from CHANGELOG.md):
```markdown
## [1.0.0-rc1] - 2026-01-13

### Added
- **Phase 9**: Release Candidate with demo mode and smoke runbook
  - Version information API endpoint (`/api/version`)
  - Demo mode with synthetic seed data (`DEMO_MODE=true`)
  - Smoke test runbook for operator verification
  - Upgrade and rollback procedures

- **Phase 8**: Observability + Monitoring + Deployment
  - Health check endpoint (`/healthz`) - quick liveness probe
  - Readiness check endpoint (`/readyz`) - DB and schema verification
  - Prometheus metrics endpoint (`/metrics`)
  - Monitoring dashboard (`/admin/monitoring`)
  - Provider reliability tracking
  - Source drift detection (fingerprinting)
  - Request correlation IDs
  - Structured logging (JSON/text toggle)
  - SLO metrics (30-day success rates)
  - Production Docker Compose configuration
  - Systemd service template
  - GitHub Actions CI pipeline

... (full changelog in CHANGELOG.md)

### Breaking Changes
- **None** - Fully backwards compatible release
```

---

### 2. Copy-Paste Commands

#### Seed Demo Data

```bash
# Seed 180 days of demo data (default)
docker compose run --rm app python -m app.ops seed-demo

# Seed custom number of days
docker compose run --rm app python -m app.ops seed-demo --days 90

# Seed to specific database path
docker compose run --rm app python -m app.ops seed-demo --db data/demo.db --days 30

# Enable demo mode banner
echo "DEMO_MODE=true" >> .env
docker compose restart
```

**Expected Output**:
```
Seeding demo data for 180 days...
  Generating data for 130 business days...
  Seeding yield curve data...
  Seeding interbank rates...
  Seeding auction results...
  Seeding secondary trading...
  Seeding policy rates...
  Seeding ingest runs...
  Seeding DQ runs...
  Seeding alerts...
  Seeding source fingerprints...

✓ Demo data seeded successfully!
  Date range: 2024-07-17 to 2026-01-13
  Total business days: 130
  Database: data/bond_lab.db

To enable demo mode banner, set: DEMO_MODE=true
```

#### Start Production

```bash
# 1. Configure environment
cp .env.example .env
nano .env  # Edit as needed

# 2. Build and start production containers
docker compose -f docker-compose.prod.yml up -d --build

# 3. Wait for startup (10-20 seconds)
sleep 15

# 4. Check status
docker compose -f docker-compose.prod.yml ps

# 5. View logs
docker compose -f docker-compose.prod.yml logs -f
```

#### Run Smoke Checklist

```bash
# 1. Health Checks
curl http://localhost:8000/healthz
# Expected: {"status":"ok","timestamp":"..."}

curl http://localhost:8000/readyz
# Expected: {"status":"ok","database":{...}}

curl http://localhost:8000/api/version | jq
# Expected: {"version":"1.0.0-rc1",...}

# 2. Key Pages (macOS)
open http://localhost:8000/                  # Dashboard
open http://localhost:8000/yield-curve       # Yield Curve
open http://localhost:8000/transmission      # Transmission
open http://localhost:8000/stress            # Stress Model
open http://localhost:8000/snapshot/today    # Daily Snapshot

# 3. Admin Pages
open http://localhost:8000/admin/monitoring # Monitoring Dashboard
open http://localhost:8000/admin/quality    # Quality Dashboard
curl -I http://localhost:8000/alerts        # Alerts API

# 4. PDF Report
curl -o daily_report.pdf http://localhost:8000/report/daily.pdf
ls -lh daily_report.pdf
# Expected: size > 0 bytes

# 5. Admin Auth (if enabled)
ADMIN_USER="admin"
ADMIN_PASSWORD="your_password"
curl -u "${ADMIN_USER}:${ADMIN_PASSWORD}" \
  http://localhost:8000/admin/monitoring
```

#### Create & Verify Backup

```bash
# 1. Create backup
docker compose exec -T app python -m app.ops backup

# 2. Verify backup exists
ls -lh ./backups/ | tail -1

# 3. Verify backup integrity
latest_backup=$(ls -t ./backups/*.duckdb 2>/dev/null | head -1)
docker compose exec -T app python -m app.ops verify-backup \
  --in "$latest_backup"

# Expected: ✓ Backup is valid
```

---

### 3. Demo Mode Features

#### CLI Command

```bash
python -m app.ops seed-demo --days 180
```

**Generates**:
- Synthetic yield curve data (2Y, 5Y, 10Y)
- Synthetic interbank rates (ON, 1W, 1M)
- Synthetic auction results
- Synthetic secondary trading data
- Synthetic policy rates
- Ingest run records
- DQ run records (some with WARN)
- Alert records
- Source fingerprints

**Provenance**:
- All demo data has `source='DEMO'`
- All demo data has `provider='demo'` (for fingerprints)
- Easy to distinguish from real data

#### Environment Variable

```bash
# In .env
DEMO_MODE=false  # Default: off
```

**When enabled (`DEMO_MODE=true`)**:
- UI shows purple banner: "⚠️ DEMO MODE - Showing synthetic demonstration data"
- Banner visible on all pages
- Clear indication data is not real

#### Version Endpoint

```bash
curl http://localhost:8000/api/version
```

**Response** (when `DEMO_MODE=true`):
```json
{
  "version": "1.0.0-rc1",
  "build_date": "2026-01-13T10:00:00.000000",
  "feature_flags": {
    "admin_auth_enabled": false,
    "scheduler_enabled": false,
    "global_data_enabled": false,
    "demo_mode_enabled": true
  }
}
```

---

### 4. Tests Added (5 new tests)

#### TestDemoMode Class

```python
class TestDemoMode:
    """Test demo mode functionality"""

    def test_seed_demo_generates_data(...)
        # Verifies seed-demo CLI generates all expected tables
        # Checks yield curve, interbank, auctions, secondary, policy
        # Checks ingest runs, DQ runs, alerts, fingerprints

    def test_snapshot_works_with_demo_data(...)
        # Verifies /snapshot/today works with demo data

    def test_version_endpoint_includes_demo_mode_flag(...)
        # Verifies /api/version includes demo_mode_enabled flag

    def test_readyz_ok_in_demo_mode(...)
        # Verifies /readyz returns OK in demo mode

    def test_demo_data_has_correct_provenance(...)
        # Verifies demo data has source='DEMO' marking
```

**Test Command**:
```bash
docker compose run --rm app pytest tests/test_observability.py::TestDemoMode -v
```

---

## Non-Negotiables Compliance

✅ **No Breaking Changes**: All existing functionality preserved
✅ **Safe-by-Default**: Demo mode OFF by default, auth OFF by default
✅ **Works Offline**: Demo mode requires no provider calls
✅ **Tests Pass in Docker**: All 5 new tests pass in Docker environment
✅ **Secrets Never Logged**: No secrets in logs or demo data
✅ **Backwards Compatible**: Existing data and configs work unchanged

---

## Quick Start Guide

### For Demo/Testing

```bash
# 1. Clone and configure
git clone https://github.com/yourusername/vn-bond-lab.git
cd vn-bond-lab
cp .env.example .env

# 2. Seed demo data
docker compose run --rm app python -m app.ops seed-demo --days 90

# 3. Enable demo mode
echo "DEMO_MODE=true" >> .env

# 4. Start application
docker compose up -d --build

# 5. Open browser
open http://localhost:8000
# You'll see: "⚠️ DEMO MODE - Showing synthetic demonstration data"
```

### For Production

```bash
# 1. Configure
cp .env.example .env
nano .env  # Set secure passwords, etc.

# 2. Start production
docker compose -f docker-compose.prod.yml up -d --build

# 3. Run smoke tests
# See docs/RUNBOOK_SMOKE.md

# 4. Create backup
docker compose -f docker-compose.prod.yml exec -T app python -m app.ops backup

# 5. Verify
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
```

---

## Documentation Index

- **CHANGELOG.md**: Full changelog by phase
- **docs/RUNBOOK_SMOKE.md**: Operator smoke test procedures
- **docs/UPGRADE.md**: Upgrade and rollback procedures
- **docs/DEPLOYMENT.md**: Production deployment guide
- **docs/PHASE8_SUMMARY.md**: Phase 8 observability features
- **docs/PHASE8.1_SUMMARY.md**: Config cleanup and verification
- **docs/PHASE9_SUMMARY.md**: This document

---

## API Endpoints

### New Endpoints

```bash
# Version endpoint (added in Phase 9)
GET /api/version
Response:
{
  "version": "1.0.0-rc1",
  "build_date": "2026-01-13T10:00:00.000000",
  "feature_flags": {
    "admin_auth_enabled": false,
    "scheduler_enabled": false,
    "global_data_enabled": false,
    "demo_mode_enabled": false
  }
}
```

### Existing Endpoints (Reference)

```bash
# Health & Readiness (Phase 8)
GET /healthz          # Quick health check
GET /readyz           # Readiness with DB verification
GET /metrics          # Prometheus metrics

# Admin (Phase 7-8)
GET /admin/monitoring # Monitoring dashboard
GET /admin/quality    # Data quality dashboard
GET /alerts           # Alert management

# Analytics (Phase 6)
GET /transmission     # Transmission analytics
GET /stress           # BondY stress model

# Data (Phase 2-5)
GET /                 # Dashboard
GET /yield-curve      # Yield curve visualization
GET /interbank        # Interbank rates
GET /auctions         # Auction results
GET /secondary        # Secondary trading
GET /policy           # Policy rates

# Reports
GET /snapshot/today   # Vietnamese daily snapshot
GET /report/daily.pdf # Daily PDF report
```

---

## Troubleshooting

### Issue: seed-demo command fails

**Solution**:
```bash
# Use Docker (not system Python)
docker compose run --rm app python -m app.ops seed-demo --days 30
```

### Issue: Demo mode banner not showing

**Solution**:
```bash
# Verify DEMO_MODE is set
docker compose exec -T app env | grep DEMO_MODE

# Restart container after changing .env
docker compose restart
```

### Issue: Version shows old number

**Solution**:
```bash
# Force rebuild
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

## Success Criteria

✅ Version bumped to 1.0.0-rc1
✅ CHANGELOG.md created with all phases documented
✅ /api/version endpoint returns version and feature flags
✅ Smoke runbook created with copy-paste procedures
✅ Demo mode CLI command seeds realistic synthetic data
✅ Demo data has correct provenance (source='DEMO')
✅ UI shows demo banner when DEMO_MODE=true
✅ Upgrade/rollback procedures documented
✅ All tests pass in Docker
✅ No breaking changes
✅ Works offline for demo mode

---

**Phase 9 Status**: ✅ COMPLETE

**Next Steps**:
1. Tag release: `git tag v1.0.0-rc1`
2. Create release notes from CHANGELOG.md
3. Deploy to staging and run smoke tests
4. Gather user feedback
5. Prepare for 1.0.0 final release
