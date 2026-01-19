# Upgrade and Rollback Guide

This guide provides safe procedures for upgrading VN Bond Lab to new versions and rolling back if needed.

---

## Table of Contents

1. [Pre-Upgrade Checklist](#pre-upgrade-checklist)
2. [Upgrade Procedure](#upgrade-procedure)
3. [Post-Upgrade Verification](#post-upgrade-verification)
4. [Rollback Procedure](#rollback-procedure)
5. [Emergency Recovery](#emergency-recovery)

---

## Pre-Upgrade Checklist

### 1. Check Current Version

```bash
# Check current version
curl http://localhost:8000/api/version | jq

# Expected output
{
  "version": "1.0.0-rc1",
  "build_date": "2026-01-13T10:00:00.000000",
  "feature_flags": {...}
}
```

### 2. Review Release Notes

```bash
# Check CHANGELOG for new version
cat CHANGELOG.md | grep -A 20 "## \[1.0.0"
```

Look for:
- New features
- Breaking changes
- Deprecated features
- Migration requirements

### 3. Backup Current Deployment

**CRITICAL**: Always backup before upgrading!

```bash
# For dev environment
docker compose exec -T app python -m app.ops backup

# For prod environment
docker compose -f docker-compose.prod.yml exec -T app python -m app.ops backup
```

**Expected Output**:
```
✓ Backup created: ./backups/bonds_backup_20250113_103000.duckdb
✓ Backup verified successfully
  Tables: 15
```

### 4. Verify Backup

```bash
# Verify backup file exists
ls -lh ./backups/ | tail -1

# Verify backup integrity
docker compose exec -T app python -m app.ops verify-backup \
  --in ./backups/bonds_backup_20250113_103000.duckdb
```

**Expected Output**:
```
✓ Backup is valid
  Total Tables: 15
  Valid: Yes
```

### 5. Stop Services (Optional for Zero-Downtime)

```bash
# Stop current deployment
docker compose down

# Or for prod
docker compose -f docker-compose.prod.yml down
```

---

## Upgrade Procedure

### Option 1: Git Upgrade (Recommended)

```bash
# 1. Fetch latest changes
git fetch origin
git log -1 origin/main  # Review latest commit

# 2. Pull latest code
git pull origin main

# 3. Check for configuration changes
git diff HEAD~1 .env.example

# 4. Update .env if needed (copy new variables)
nano .env

# 5. Rebuild and start
docker compose -f docker-compose.prod.yml up -d --build

# 6. Monitor logs
docker compose -f docker-compose.prod.yml logs -f
```

### Option 2: Manual Upgrade

```bash
# 1. Download new release
wget https://github.com/yourusername/vn-bond-lab/archive/v1.0.0.tar.gz

# 2. Extract
tar -xzf v1.0.0.tar.gz
cd vn-bond-lab-1.0.0

# 3. Copy configuration
cp ../.env .

# 4. Update configuration if needed
nano .env

# 5. Build and start
docker compose -f docker-compose.prod.yml up -d --build
```

### Schema Migration

Schema migrations are **idempotent** and run automatically on startup.

```bash
# No manual migration needed - schema initializes automatically
# Just verify after startup that it worked
curl http://localhost:8000/readyz | jq '.database.schema_initialized'
```

**Expected Output**:
```json
{
  "status": "ok",
  "database": {
    "schema_initialized": true
  }
}
```

---

## Post-Upgrade Verification

### 1. Health Checks

```bash
# Quick health check
curl http://localhost:8000/healthz

# Readiness check
curl http://localhost:8000/readyz

# Version check (should show new version)
curl http://localhost:8000/api/version | jq
```

### 2. Smoke Test Key Pages

```bash
# Test main pages
curl -I http://localhost:8000/
curl -I http://localhost:8000/yield-curve
curl -I http://localhost:8000/transmission
curl -I http://localhost:8000/stress

# Test admin pages (if auth disabled)
curl -I http://localhost:8000/admin/monitoring
curl -I http://localhost:8000/admin/quality
```

**Expected**: All return `HTTP/1.1 200 OK`

### 3. Verify Data Integrity

```bash
# Check latest data exists
docker compose exec -T app python -c "
from app.db.schema import DatabaseManager
from app.config import settings

db = DatabaseManager(settings.db_path)
db.connect()

# Check yield curve count
yc_count = db.con.execute('SELECT COUNT(*) FROM gov_yield_curve').fetchone()[0]
print(f'Yield curve records: {yc_count}')

# Check interbank count
ib_count = db.con.execute('SELECT COUNT(*) FROM interbank_rates').fetchone()[0]
print(f'Interbank rate records: {ib_count}')

db.close()
"
```

**Expected**: Count should be greater than 0 (if you have data)

### 4. Run Tests (Optional but Recommended)

```bash
# Run test suite
docker compose run --rm app pytest -q
```

**Expected**: All tests pass

### 5. Check Logs for Errors

```bash
# Check for errors in startup logs
docker compose logs 2>&1 | grep -i error

# Check for warnings
docker compose logs 2>&1 | grep -i warn
```

**Expected**: No critical errors

---

## Rollback Procedure

### When to Rollback

- Upgrade fails to start
- Data corruption detected
- Critical bugs in new version
- Performance degradation
- Incompatible changes

### Rollback Steps

#### 1. Stop Current Deployment

```bash
# Stop services
docker compose down

# Or for prod
docker compose -f docker-compose.prod.yml down
```

#### 2. Revert Code

```bash
# If using Git
git log --oneline -10  # Find previous version commit
git checkout <previous-commit-hash>

# Or if you have a backup of the old code
cd ..
mv vn-bond-lab vn-bond-lab-new
mv vn-bond-lab-backup vn-bond-lab
cd vn-bond-lab
```

#### 3. Restore Database from Backup

```bash
# Find latest backup
ls -lt ./backups/*.duckdb | head -1

# Set restore permissions
export ALLOW_RESTORE=true

# Restore from backup
docker compose run --rm \
  -e ALLOW_RESTORE=true \
  app python -m app.ops restore \
  --in ./backups/bonds_backup_20250113_103000.duckdb \
  --yes
```

**Expected Output**:
```
[INFO] Restoring from backup: ./backups/bonds_backup_20250113_103000.duckdb
[INFO] Backup validated successfully
[INFO] Restoring tables...
✓ Database restored successfully
⚠ Make sure to restart the application
```

#### 4. Restart with Old Version

```bash
# Start services
docker compose up -d

# Or for prod
docker compose -f docker-compose.prod.yml up -d
```

#### 5. Verify Rollback

```bash
# Check version (should show old version)
curl http://localhost:8000/api/version | jq '.version'

# Check health
curl http://localhost:8000/healthz

# Check data
docker compose exec -T app python -c "
from app.db.schema import DatabaseManager
from app.config import settings

db = DatabaseManager(settings.db_path)
db.connect()
count = db.con.execute('SELECT COUNT(*) FROM gov_yield_curve').fetchone()[0]
print(f'Records: {count}')
db.close()
"
```

---

## Emergency Recovery

### Database Corruption

If the database is corrupted:

```bash
# 1. Stop services immediately
docker compose down

# 2. Backup corrupted database (just in case)
cp data/duckdb/bonds.duckdb data/duckdb/bonds.duckdb.corrupted

# 3. Restore from known good backup
export ALLOW_RESTORE=true
docker compose run --rm \
  -e ALLOW_RESTORE=true \
  app python -m app.ops restore \
  --in ./backups/bonds_backup_YYYYMMDD_HHMMSS.duckdb \
  --yes

# 4. Start services
docker compose up -d

# 5. Verify
curl http://localhost:8000/healthz
```

### Container Won't Start

```bash
# 1. Check logs
docker compose logs

# 2. Check for port conflicts
lsof -i :8000

# 3. Check disk space
df -h

# 4. Rebuild from scratch
docker compose down
docker system prune -a  # ⚠️ This removes all Docker data
docker compose up -d --build
```

### Configuration Issues

```bash
# 1. Compare with example
diff .env .env.example

# 2. Reset to defaults (copy example)
cp .env.example .env
nano .env  # Reconfigure

# 3. Restart
docker compose down
docker compose up -d
```

---

## Upgrade Testing Checklist

Before deploying to production:

- [ ] Reviewed CHANGELOG for new version
- [ ] Tested upgrade in dev/staging environment
- [ ] Verified all backups are valid
- [ ] Confirmed rollback procedure works
- [ ] Notified users of planned upgrade
- [ ] Scheduled maintenance window (if needed)
- [ ] Prepared emergency contacts
- [ ] Tested new features in dev environment
- [ ] Verified compatibility with external systems
- [ ] Checked disk space for new version

---

## Zero-Downtime Upgrade (Advanced)

For production environments requiring high availability:

### Using Blue-Green Deployment

```bash
# 1. Start new version on different port
cd vn-bond-lab-new
cp ../vn-bond-lab/.env .
echo "PORT=8001" >> .env
docker compose -f docker-compose.prod.yml up -d

# 2. Test new version
curl http://localhost:8001/healthz
curl http://localhost:8001/api/version

# 3. Switch traffic (update reverse proxy)
# If using nginx:
# nginx -s reload

# 4. Stop old version
cd ../vn-bond-lab
docker compose -f docker-compose.prod.yml down
```

### Using Database Replication

For critical deployments, consider setting up database replication before upgrading:

1. Setup read replica
2. Test upgrade on replica
3. Promote replica if upgrade successful

---

## Common Upgrade Issues

### Issue: New Environment Variables Required

**Symptom**: Container fails to start with "Missing environment variable"

**Fix**:
```bash
# Compare .env files
diff .env .env.example

# Add missing variables
nano .env

# Restart
docker compose up -d
```

### Issue: Schema Migration Fails

**Symptom**: Database initialization errors in logs

**Fix**:
```bash
# Schema is idempotent - safe to re-run
docker compose down
docker compose up -d

# If still failing, restore from backup
export ALLOW_RESTORE=true
docker compose run --rm \
  -e ALLOW_RESTORE=true \
  app python -m app.ops restore \
  --in ./backups/latest_backup.duckdb \
  --yes
```

### Issue: Version Shows Old Number

**Symptom**: `/api/version` shows old version after upgrade

**Fix**:
```bash
# Force rebuild
docker compose down
docker compose build --no-cache
docker compose up -d

# Verify
curl http://localhost:8000/api/version | jq
```

---

## Support

For issues or questions:
- **Documentation**: See `docs/` directory
- **Issues**: https://github.com/yourusername/vn-bond-lab/issues
- **Runbook**: `docs/RUNBOOK_SMOKE.md`
- **Deployment**: `docs/DEPLOYMENT.md`

---

**Remember**: Always backup before upgrading! Test upgrades in non-production environments first.
