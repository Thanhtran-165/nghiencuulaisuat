# Smoke Test Runbook - Operator Verification Guide

This runbook provides copy-paste steps to verify VN Bond Lab is working correctly after deployment, upgrades, or configuration changes.

**Prerequisites**:
- Docker and Docker Compose installed
- Application cloned and configured
- `.env` file configured (see `docs/DEPLOYMENT.md`)

---

## Operator Commands (Verified)

These core commands are tested and verified for production use:

```bash
# Build & Start Production
docker compose -f docker-compose.prod.yml up -d --build

# Health Verification
curl http://localhost:8000/healthz          # Quick health (no DB)
curl http://localhost:8000/readyz           # Readiness (includes DB)
curl http://localhost:8000/api/version | jq # Version info
curl http://localhost:8000/metrics | head   # Prometheus metrics

# Generate/Download PDF
curl -o daily_report.pdf http://localhost:8000/report/daily.pdf

# Open Key Admin Pages (in browser)
open http://localhost:8000/admin/monitoring  # Monitoring Dashboard
open http://localhost:8000/admin/quality     # Data Quality Dashboard
open http://localhost:8000/admin/alerts      # Alert Thresholds

# Backup + Verify (DuckDB)
docker compose exec -T app python -m app.ops backup
latest_backup=$(ls -t data/backups/*.duckdb 2>/dev/null | head -1)
docker compose exec -T app python -m app.ops verify-backup --in "$latest_backup"
```

---

## Table of Contents

1. [Build & Start](#1-build--start)
2. [Verify Health Endpoints](#2-verify-health-endpoints)
3. [Verify Key Pages](#3-verify-key-pages)
4. [Verify Admin Endpoints](#4-verify-admin-endpoints)
5. [Backup & Verify](#5-backup--verify)
6. [Common Failures & Fixes](#6-common-failures--fixes)

---

## 1. Build & Start

### Development Mode

```bash
# Build and start in development mode
docker compose up --build -d

# View logs
docker compose logs -f

# Check container status
docker compose ps
```

### Production Mode

```bash
# Copy environment template if not exists
cp .env.example .env

# Edit configuration
nano .env

# Build and start in production mode
docker compose -f docker-compose.prod.yml up -d

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Check container status
docker compose -f docker-compose.prod.yml ps
```

### Expected Output

Container should show `healthy` status:
```bash
$ docker compose ps
NAME                    STATUS          PORTS
vn-bond-lab-app         Up (healthy)    0.0.0.0:8000->8000/tcp
```

---

## 2. Verify Health Endpoints

### Quick Health Check

```bash
# Health check (no DB query)
curl -i http://localhost:8000/healthz
```

**Expected Output**:
```http
HTTP/1.1 200 OK
content-type: application/json

{
  "status": "ok",
  "timestamp": "2026-01-13T10:30:00.123456"
}
```

### Readiness Check

```bash
# Readiness check (includes DB verification)
curl -i http://localhost:8000/readyz
```

**Expected Output**:
```http
HTTP/1.1 200 OK
content-type: application/json

{
  "status": "ready",
  "database": "connected",
  "tables": 15,
  "last_ingest_run": {...},
  "last_dq_status": {...},
  "demo_mode_enabled": false
}
```

### Version Check

```bash
# Version and feature flags
curl http://localhost:8000/api/version | jq
```

**Expected Output**:
```json
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

### Metrics Check

```bash
# Prometheus metrics
curl http://localhost:8000/metrics | head
```

**Expected Output** (should show Prometheus format):
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
...
```

---

## 3. Verify Key Pages

### Main Dashboard

```bash
# Option 1: curl
curl -I http://localhost:8000/

# Option 2: open in browser (macOS)
open http://localhost:8000/

# Option 3: open in browser (Linux with xdg-open)
xdg-open http://localhost:8000/
```

**Expected**: Dashboard loads with:
- Latest government bond yields (2Y, 5Y, 10Y)
- Yield curve spread (10Y-2Y)
- Overnight interbank rate
- Interactive charts

### Yield Curve Page

```bash
# Check yield curve page
curl -I http://localhost:8000/yield-curve

# Open in browser
open http://localhost:8000/yield-curve
```

**Expected**: Page loads with date selector and yield curve visualization

### Transmission Analytics

```bash
# Check transmission analytics page
curl -I http://localhost:8000/transmission

# Open in browser
open http://localhost:8000/transmission
```

**Expected**: Page loads with:
- Transmission metrics visualization
- Policy rate impact analysis
- Recent alerts if any

### Stress Model Dashboard

```bash
# Check stress model page
curl -I http://localhost:8000/stress

# Open in browser
open http://localhost:8000/stress
```

**Expected**: Page loads with:
- BondY stress scenarios
- Transmission vs stress comparison
- Global rate indicators

### Daily Snapshot (Vietnamese)

```bash
# Check snapshot page
curl -I http://localhost:8000/snapshot/today

# Open in browser
open http://localhost:8000/snapshot/today
```

**Expected**: Vietnamese snapshot page loads with today's data summary

### Daily PDF Report

```bash
# Generate daily PDF report
curl -I http://localhost:8000/report/daily.pdf

# Download PDF
curl -o daily_report.pdf http://localhost:8000/report/daily.pdf

# Check PDF size (should be > 0)
ls -lh daily_report.pdf
```

**Expected**: PDF file downloads successfully with size > 0 bytes

---

## 4. Verify Admin Endpoints

### Check if Admin Auth is Enabled

```bash
# Check version endpoint for auth flag
curl -s http://localhost:8000/api/version | jq '.feature_flags.admin_auth_enabled'
```

### If Auth Disabled (Default)

```bash
# Test admin monitoring endpoint
curl -I http://localhost:8000/admin/monitoring

# Test admin quality endpoint
curl -I http://localhost:8000/admin/quality

# Test admin alerts endpoint
curl -I http://localhost:8000/admin/alerts

# Test admin ops endpoint
curl -I http://localhost:8000/admin/ops

# Test admin notifications endpoint
curl -I http://localhost:8000/admin/notifications

# Test admin ingest endpoint
curl -I http://localhost:8000/admin/ingest
```

**Expected**: All endpoints return `HTTP/1.1 200 OK`

### If Auth Enabled

```bash
# Set credentials
ADMIN_USER="admin"
ADMIN_PASSWORD="your_password"

# Test monitoring endpoint with auth
curl -I -u "${ADMIN_USER}:${ADMIN_PASSWORD}" http://localhost:8000/admin/monitoring

# Test quality endpoint with auth
curl -I -u "${ADMIN_USER}:${ADMIN_PASSWORD}" http://localhost:8000/admin/quality

# Test alerts endpoint with auth
curl -I -u "${ADMIN_USER}:${ADMIN_PASSWORD}" http://localhost:8000/admin/alerts

# Test ops endpoint with auth
curl -I -u "${ADMIN_USER}:${ADMIN_PASSWORD}" http://localhost:8000/admin/ops

# Test notifications endpoint with auth
curl -I -u "${ADMIN_USER}:${ADMIN_PASSWORD}" http://localhost:8000/admin/notifications

# Test ingest endpoint with auth
curl -I -u "${ADMIN_USER}:${ADMIN_PASSWORD}" http://localhost:8000/admin/ingest
```

**Expected**:
- Correct credentials: `HTTP/1.1 200 OK`
- Incorrect credentials: `HTTP/1.1 401 Unauthorized`

### Open Monitoring Dashboard

```bash
# Open in browser (auth disabled)
open http://localhost:8000/admin/monitoring

# Or with auth (will prompt for credentials)
open http://localhost:8000/admin/monitoring
```

**Expected**: Monitoring dashboard loads showing:
- Pipeline Status (last ingest, last DQ)
- SLO Metrics (30-day success rates)
- Provider Reliability table
- Drift Signals table

---

## 5. Backup & Verify

### Create Backup

```bash
# For dev environment
docker compose exec -T app python -m app.ops backup

# For prod environment
docker compose -f docker-compose.prod.yml exec -T app python -m app.ops backup
```

**Expected Output**:
```
✓ Backup created: data/backups/bonds_backup_YYYYMMDD_HHMMSS.duckdb
✓ Backup verified successfully
  Tables: 15
```

### Verify Backup File

```bash
# List backups
ls -lh data/backups/ | tail -5

# Check latest backup exists and has size > 0
latest_backup=$(ls -t data/backups/*.duckdb 2>/dev/null | head -1)
if [ -n "$latest_backup" ]; then
    echo "Latest backup: $latest_backup"
    size=$(du -h "$latest_backup" | cut -f1)
    echo "Size: $size"
else
    echo "No backups found!"
fi
```

**Expected**:
- Backup file exists in `data/backups/` directory
- File size is > 0
- Filename format: `bonds_backup_YYYYMMDD_HHMMSS.duckdb`

### Verify Backup Integrity (DuckDB)

```bash
# Verify using the ops CLI
latest_backup=$(ls -t data/backups/*.duckdb 2>/dev/null | head -1)
docker compose exec -T app python -m app.ops verify-backup --in "$latest_backup"
```

**Expected Output**:
```
Backup Verification: data/backups/bonds_backup_YYYYMMDD_HHMMSS.duckdb
  Readable: Yes
  Total Tables: 15
  Valid: Yes

✓ Backup is valid
```

---

## 6. Common Failures & Fixes

### Troubleshooting Decision Tree

**Quick diagnosis guide:**

1. **DQ ERROR blocks compute?**
   - ✗ Do NOT tweak alert thresholds
   - ✓ Fix ingestion/source data issue
   - ✓ Re-run DQ: `curl -X POST "http://localhost:8000/api/admin/quality/run?date=YYYY-MM-DD"`
   - ✓ Only then compute transmission/stress metrics

2. **Alert noise (too many alerts firing)?**
   - ✓ Adjust alert thresholds in `/admin/alerts`
   - ✓ Use `/api/admin/alerts` to modify thresholds
   - ✓ Do NOT confuse with DQ rules

3. **Missing data in dashboards?**
   - ✓ Check provider status: `/admin/ingest`
   - ✓ Check data coverage: `/api/admin/coverage`
   - ✓ Backfill if needed: `/api/admin/ingest/backfill`

---

### Issue: Container Won't Start

**Symptoms**:
```bash
$ docker compose ps
NAME                    STATUS
vn-bond-lab-app         Exit 1
```

**Diagnosis**:
```bash
# Check logs
docker compose logs | tail -50

# Common errors in logs
```

**Fixes**:

1. **Port already in use**:
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill process using port 8000
kill -9 $(lsof -t -i:8000)

# Or change port in .env
echo "PORT=8001" >> .env
docker compose up -d
```

2. **Database path issue**:
```bash
# Ensure data directory exists
mkdir -p data/duckdb

# Check permissions
ls -la data/

# Fix permissions if needed
chmod 755 data/
chmod 755 data/duckdb/
```

3. **Missing .env file**:
```bash
# Copy example .env
cp .env.example .env

# Restart
docker compose up -d
```

---

### Issue: "python command not found"

**Symptoms**:
```bash
$ python -m pytest
python: command not found
```

**Fix**: **Always use Docker to run tests**

```bash
# ❌ DON'T use system Python
python -m pytest  # This will fail

# ✅ DO use Docker
docker compose run --rm app pytest -q  # This works
```

---

### Issue: Providers Blocked / Rate Limited

**Symptoms**:
```bash
# In logs
[ERROR] Failed to fetch from HNX: 403 Forbidden
[ERROR] Provider HNX blocked request
```

**Diagnosis**:
```bash
# Check provider status
curl -I https://hnx.vn
curl -I https://www.sbv.gov.vn
```

**Fixes**:

1. **Wait and retry**:
```bash
# Rate limits usually expire after 1 hour
# Check logs for when to retry
docker compose logs | grep "rate limit"
```

2. **Increase rate limit delay**:
```bash
# In .env
RATE_LIMIT_SECONDS=5.0  # Increase from default 1.0

# Restart
docker compose up -d
```

3. **Use demo mode for testing**:
```bash
# Enable demo mode
echo "DEMO_MODE=true" >> .env

# Seed demo data
docker compose exec -T app python -m app.ops seed-demo --days 30

# Restart
docker compose up -d
```

---

### Issue: Admin Auth Misconfiguration

**Symptoms**:
```bash
$ curl http://localhost:8000/admin/monitoring
HTTP/1.1 401 Unauthorized

# But auth should be disabled
$ grep ADMIN_AUTH .env
ADMIN_AUTH_ENABLED=false
```

**Fix**:

1. **Check environment variable**:
```bash
# Ensure variable is set correctly
docker compose exec -T app env | grep ADMIN_AUTH

# Should show: ADMIN_AUTH_ENABLED=false
```

2. **Restart container**:
```bash
# .env changes require restart
docker compose down
docker compose up -d
```

3. **Test with correct credentials**:
```bash
# If auth is enabled, use correct password
curl -u admin:your_password http://localhost:8000/admin/monitoring
```

---

### Issue: DQ Failure Blocks Compute

**Symptoms**:
```bash
# In logs
[ERROR] DQ run failed: RULE_YC_TENOR_COVERAGE ERROR
[INFO] Compute blocked by DQ ERROR status

# Transmission page shows no data
```

**Diagnosis**:
```bash
# Check DQ status
curl http://localhost:8000/api/admin/quality/latest | jq

# Check which rules failed
curl http://localhost:8000/api/admin/quality/rules?status=ERROR
```

**Fixes**:

1. **Review failed rules**:
```bash
# Open admin quality dashboard
open http://localhost:8000/admin/quality

# Check which rules failed and why
curl http://localhost:8000/api/admin/quality/latest | jq
```

2. **Review DQ rule results**:
```bash
# Open data quality dashboard
open http://localhost:8000/admin/quality

# Or check DQ results via API
curl "http://localhost:8000/api/admin/quality/results?severity=ERROR" | jq
```

**Important**: DQ rules (RULE_*) are **NOT editable via the UI or API**. They are defined in code and check data quality. To fix DQ failures:
- Fix the underlying data issue (missing data, provider problems)
- Re-run DQ after fixing: `curl -X POST "http://localhost:8000/api/admin/quality/run?date=YYYY-MM-DD"`

3. **Adjust alert thresholds** (for transmission/stress alerts, NOT DQ rules):
```bash
# Open alert thresholds dashboard
open http://localhost:8000/admin/alerts

# View current alert thresholds
curl http://localhost:8000/api/admin/alerts | jq

# Example: Disable transmission high alert
curl -X POST "http://localhost:8000/api/admin/alerts/ALERT_TRANSMISSION_HIGH?enabled=false&severity=HIGH"

# Example: Change stress alert severity to MEDIUM
curl -X POST "http://localhost:8000/api/admin/alerts/ALERT_STRESS_HIGH?enabled=true&severity=MEDIUM"

# Example: Configure liquidity spike alert with custom threshold
curl -X POST "http://localhost:8000/api/admin/alerts/ALERT_LIQUIDITY_SPIKE?enabled=true&severity=MEDIUM&params=%7B%22threshold%22%3A2.5%7D"
```

**Note**: Alert codes (ALERT_*) are separate from DQ rules (RULE_*). Alert thresholds control when notifications are fired based on computed metrics. The `params` value must be URL-encoded JSON; use double quotes in JSON (e.g., `{"threshold": 2.5}` encodes to `%7B%22threshold%22%3A2.5%7D`).

4. **Backfill missing data**:
```bash
# Trigger backfill for missing date range
curl -X POST "http://localhost:8000/api/admin/ingest/backfill?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&providers=HNX_YIELD"
```

5. **Override DQ block** (emergency only):
```bash
# ⚠️ WARNING: Only use this in emergencies
# This allows compute to proceed despite DQ failures
docker compose exec -T app python -c "
from app.db.schema import DatabaseManager
from app.config import settings

db = DatabaseManager(settings.db_path)
db.connect()

# Override latest DQ run to WARN
db.con.execute('''
    UPDATE dq_runs
    SET status = 'WARN'
    WHERE run_id = (SELECT MAX(run_id) FROM dq_runs)
''')

print('DQ status overridden to WARN')
db.close()
"
```

---

### Issue: Database Corruption

**Symptoms**:
```bash
[ERROR] Database error: Database corruption
[ERROR] Failed to query database
```

**Diagnosis**:
```bash
# Check database file
docker compose exec -T app python -c "
from app.config import settings
import os
print(f'DB path: {settings.db_path}')
print(f'DB exists: {os.path.exists(settings.db_path)}')
print(f'DB size: {os.path.getsize(settings.db_path) if os.path.exists(settings.db_path) else 0} bytes')
"
```

**Fix**: **Restore from backup**

```bash
# 1. Stop container
docker compose down

# 2. Backup corrupted database (just in case)
cp data/duckdb/bonds.duckdb data/duckdb/bonds.duckdb.corrupted

# 3. Find latest backup
latest_backup=$(ls -t data/backups/*.duckdb 2>/dev/null | head -1)
echo "Latest backup: $latest_backup"

# 4. Restore from backup
docker compose run --rm \
  -e ALLOW_RESTORE=true \
  app python -m app.ops restore --in "$latest_backup" --yes

# 5. Start container
docker compose up -d

# 6. Verify
curl http://localhost:8000/healthz
```

---

## Operator Commands (Verified End-to-End)

These commands are tested and verified to work correctly. Use this as your quick reference for common operations.

### Build & Start

```bash
# Development mode
docker compose up -d --build

# Production mode
docker compose -f docker-compose.prod.yml up -d --build

# View logs
docker compose -f docker-compose.prod.yml logs -f
```

### Health Verification

```bash
# Quick health (no DB)
curl http://localhost:8000/healthz

# Readiness (includes DB check)
curl http://localhost:8000/readyz

# Version info
curl http://localhost:8000/api/version | jq

# Prometheus metrics
curl http://localhost:8000/metrics | head
```

### Backup Operations

```bash
# Create backup
docker compose exec -T app python -m app.ops backup

# List backups
ls -lh data/backups/

# Verify latest backup
latest_backup=$(ls -t data/backups/*.duckdb 2>/dev/null | head -1)
docker compose exec -T app python -m app.ops verify-backup --in "$latest_backup"
```

### Admin Operations (with auth)

```bash
# Set credentials (if ADMIN_AUTH_ENABLED=true)
ADMIN_USER="admin"
ADMIN_PASSWORD="your_password"

# Check monitoring dashboard
curl -u "${ADMIN_USER}:${ADMIN_PASSWORD}" http://localhost:8000/api/admin/monitoring/summary | jq

# Check DQ status
curl -u "${ADMIN_USER}:${ADMIN_PASSWORD}" http://localhost:8000/api/admin/quality/latest | jq

# Check drift signals
curl -u "${ADMIN_USER}:${ADMIN_PASSWORD}" http://localhost:8000/api/admin/monitoring/drift | jq
```

### Restore from Backup

```bash
# Find latest backup
latest_backup=$(ls -t data/backups/*.duckdb 2>/dev/null | head -1)

# Restore (requires ALLOW_RESTORE=true)
docker compose run --rm \
  -e ALLOW_RESTORE=true \
  app python -m app.ops restore --in "$latest_backup" --yes

# Restart application
docker compose up -d
```

### Demo Mode

```bash
# Seed demo data (90 days)
docker compose run --rm app python -m app.ops seed-demo --days 90

# Enable demo mode
echo "DEMO_MODE=true" >> .env

# Restart to apply
docker compose restart

# Verify demo mode is active
curl http://localhost:8000/api/version | jq '.feature_flags.demo_mode_enabled'
```

---

## Smoke Test Checklist (Quick Reference)

```bash
# 1. Build & Start
docker compose up -d

# 2. Health Checks
curl http://localhost:8000/healthz          # Should return {"status":"ok"}
curl http://localhost:8000/readyz           # Should return {"status":"ok"}
curl http://localhost:8000/api/version | jq # Should return version info
curl http://localhost:8000/metrics | head   # Should show Prometheus format

# 3. Key Pages
open http://localhost:8000/                 # Dashboard
open http://localhost:8000/yield-curve      # Yield Curve
open http://localhost:8000/transmission     # Transmission
open http://localhost:8000/stress           # Stress Model
open http://localhost:8000/snapshot/today   # Daily Snapshot
curl -o daily.pdf http://localhost:8000/report/daily.pdf  # PDF Report

# 4. Admin (if auth disabled)
open http://localhost:8000/admin/monitoring  # Monitoring Dashboard
open http://localhost:8000/admin/quality     # Quality Dashboard
open http://localhost:8000/admin/alerts      # Alerts Dashboard
curl -I http://localhost:8000/admin/ops      # Operations

# 5. Backup
docker compose exec -T app python -m app.ops backup
ls -lh data/backups/ | tail -1

# 6. Tests (optional but recommended)
docker compose run --rm app pytest -q
```

---

## Go/No-Go Checklist (RC)

**Use this checklist before declaring RC ready for production:**

- [ ] **Build succeeds**: `docker compose -f docker-compose.prod.yml up -d --build` completes without errors
- [ ] **Smoke test passes**: `bash scripts/rc_smoke.sh` returns **PASS** (exit 0)
- [ ] **Readiness check**: `/readyz` shows:
  - `"status": "ready"`
  - `"database": "connected"`
  - `last_dq_status.status != "FAIL"` (or explains why FAIL is acceptable)
- [ ] **Snapshot renders**: `/snapshot/today` page loads with `baseline_date` populated
- [ ] **PDF generates**: `/report/daily.pdf` downloads successfully and file size > 0
- [ ] **Backup verified**: Backup created in `data/backups/` and `verify-backup` passes
- [ ] **Admin auth works** (if enabled):
  - With correct credentials: returns `200 OK`
  - Without credentials: returns `401 Unauthorized`

**If all checks pass**: System is **GO** for production deployment.

**If any check fails**: See [Rollback](#rollback-if-smoke-fails) below and [Common Failures & Fixes](#6-common-failures--fixes).

---

## Release Gate (One-Command Validation)

**For complete RC validation with auditable evidence:**

```bash
# Run automated release gate (default: 120s timeout, 2000 log lines)
bash scripts/release_gate.sh

# Optional: Increase timeout for first-time builds (300s)
READY_TIMEOUT=300 bash scripts/release_gate.sh

# Optional: Capture more logs (5000 lines)
LOG_TAIL=5000 bash scripts/release_gate.sh

# Optional: Capture logs from last 24 hours
LOG_SINCE="24h" bash scripts/release_gate.sh

# Combine multiple overrides
READY_TIMEOUT=300 LOG_TAIL=5000 bash scripts/release_gate.sh
```

**What it does:**
1. Starts production stack (`docker-compose.prod.yml`)
2. Waits for application readiness (default: 120s, override with `READY_TIMEOUT`)
3. Runs smoke tests (`scripts/rc_smoke.sh`)
4. Collects evidence artifacts to `data/release_evidence/rc_YYYYMMDD_HHMMSS/`:
   - `rc_smoke.log` - Smoke test output
   - `readyz.json` - Readiness check details
   - `version.json` - Version and feature flags
   - `snapshot.html` - Daily snapshot page
   - `daily.pdf` - Daily PDF report
   - `docker_logs.txt` - Container logs (default: last 2000 lines, override with `LOG_TAIL` or `LOG_SINCE`)
   - `SUMMARY.txt` - Evidence summary (includes configuration used)
   - `STATUS.txt` - Final PASS/FAIL result

**Evidence location:**
```bash
# List all release gate runs
ls -lh data/release_evidence/

# View latest evidence
latest=$(ls -t data/release_evidence/ | head -1)
cat "data/release_evidence/${latest}/SUMMARY.txt"
```

**Exit codes:**
- `0` = PASS (RC ready for deployment)
- `1` = FAIL (review evidence in logs)

**Use for:** Final RC sign-off with auditable trail

---

## Release Tagging (RC)

**After smoke test passes, tag the release:**

```bash
# 1. Ensure working tree is clean (no uncommitted changes)
git status
# Must show: "nothing to commit, working tree clean"

# 2. If not clean, review and commit manually
# DO NOT use "git add ." - review each file first
# Example: git add docs/RUNBOOK_SMOKE.md
#          git commit -m "Fix runbook smoke test instructions"

# 3. Create RC tag
git tag -a v1.0.0-rc1 -m "Release Candidate 1.0.0-rc1

- Production-ready observability and monitoring
- Automated smoke testing
- DuckDB backup/verification
- Data quality framework
- Admin authentication (optional)
- Demo mode safety

See RELEASE_NOTES.md for full details."

# 4. Push tag to remote
git push origin v1.0.0-rc1
# Or push all tags: git push --tags

# 5. Create GitHub Release (manual step)
# - Go to: https://github.com/YOUR_ORG/vn-bond-lab/releases/new
# - Tag: v1.0.0-rc1
# - Title: Release Candidate 1.0.0-rc1
# - Description: Copy from RELEASE_NOTES.md section for v1.0.0-rc1
```

**Verification:**
```bash
# Confirm tag exists
git tag -l "v1.0.0-*"

# Show tag details
git show v1.0.0-rc1
```

---

## Rollback (if smoke fails)

**If smoke test fails or issues discovered post-deployment:**

```bash
# 1. Find latest verified backup
latest_backup=$(ls -t data/backups/*.duckdb 2>/dev/null | head -1)

# 2. Stop production stack
docker compose -f docker-compose.prod.yml down

# 3. Restore from backup (requires ALLOW_RESTORE=true)
docker compose -f docker-compose.prod.yml run --rm \
  -e ALLOW_RESTORE=true \
  app python -m app.ops restore --in "$latest_backup" --yes

# 4. Restart production stack
docker compose -f docker-compose.prod.yml up -d

# 5. Re-run smoke test
bash scripts/rc_smoke.sh
```

**Note**: Rollback uses prod compose file to ensure correct volumes and database path.

**For detailed rollback procedures, see:** `docs/UPGRADE.md`

---

## Success Criteria

✅ All health endpoints return `200 OK` with `status: "ok"`
✅ All key pages load without errors
✅ Admin endpoints accessible (with or without auth as configured)
✅ Backup created successfully with size > 0
✅ No errors in logs (check with `docker compose logs`)

If all checks pass, the system is ready for production use!

---

## Additional Resources

- **Deployment Guide**: `docs/DEPLOYMENT.md`
- **Upgrade Guide**: `docs/UPGRADE.md`
- **Phase Summaries**: `docs/PHASE*.md`
- **API Documentation**: `http://localhost:8000/docs` (when running)
