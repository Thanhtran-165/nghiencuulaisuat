# Release Notes - Version 1.0.0

**Release Date**: 2026-01-19
**Version**: 1.0.0

Ghi chú phát hành tiếng Việt: `RELEASE_NOTES_VI.md`.

---

## Overview

VN Bond Lab v1.0.0 is the first public release. It provides Vietnamese government bond market data collection, storage, and analysis capabilities with observability, monitoring, and operational tooling.

---

## Highlights

### 🎯 Production-Ready Features

- **Observability & Monitoring**
  - `/healthz` - Quick health check endpoint
  - `/readyz` - Readiness check with database verification
  - `/metrics` - Prometheus metrics endpoint
  - `/api/version` - Version and feature flags endpoint
  - Monitoring dashboard at `/admin/monitoring`

- **Operator Tools**
  - Automated smoke test script (`scripts/rc_smoke.sh`)
  - Comprehensive backup/restore functionality
  - Demo mode with synthetic data for testing
  - Upgrade and rollback procedures

- **Data Quality**
  - Configurable DQ rules engine
  - Alert threshold management
  - Source drift detection (fingerprinting)
  - SLO metrics (30-day success rates)

### 🔒 Security & Safety

- Optional Basic Authentication for admin endpoints (`ADMIN_AUTH_*`)
- Automatic secret redaction from logs
- Demo mode prevents accidental data mixing
- Backup verification before operations

### 📊 Analytics & Reporting

- Transmission analytics (policy rate impact)
- BondY stress model scenarios
- Vietnamese daily snapshot generator
- Daily PDF report generation

---

## Data Availability (Important)

Một số dataset **không backfill được** (nguồn chỉ cung cấp “latest”), nên cần chạy ingest theo ngày để dữ liệu tích luỹ dần:

- SBV interbank (`interbank_rates`) – “latest only”
- SBV policy (`policy_rates`) – thường “current/announcement”, khó backfill lịch sử
- ABO Market Watch – chỉ dùng đối chiếu ngắn hạn, không lấp lịch sử
- Secondary trading (`gov_secondary_trading`) – lịch sử bị giới hạn bởi endpoint (earliest hiện ~2025-01-15)

Chi tiết và ảnh hưởng học thuật: `docs/MEMO_DATA_WAITING_FILL.md`.

---

## Features by Phase (carried over from RC1)

### Phase 9: Release Candidate
- Version information API
- Demo mode with seed data CLI
- Smoke test runbook
- Upgrade/rollback documentation
- Staging validation script

### Phase 8: Observability & Monitoring
- Health/readiness/metrics endpoints
- Provider reliability tracking
- Source drift detection
- Request correlation IDs
- Structured logging (JSON/text)
- Production deployment configurations

### Phase 8.1: Config Cleanup
- Standardized `ADMIN_AUTH_*` environment variables
- Backwards compatibility for deprecated `BASIC_AUTH_*`
- Verification tests for operability

### Phase 7: Data Quality Framework
- DQ rules engine with PASS/WARN/ERROR
- Admin DQ dashboard
- Alert thresholds configuration
- Backup/restore operations
- Optional Basic Authentication

### Phase 6: Advanced Analytics
- Transmission analytics
- BondY stress model
- Vietnamese daily snapshot

### Phase 5: Secondary Trading & Policy
- Secondary trading data (HNX)
- Policy rates (SBV)

### Phase 4: Auction Results & Enhanced UI
- Auction results (HNX)
- Enhanced "liquid glass" UI
- Interactive charts (Chart.js)

### Phase 3: Interbank Rates & Backfill
- Interbank rates (SBV)
- Historical backfill

### Phase 2: Yield Curve Data
- Yield curve collection (HNX)
- DuckDB database
- RESTful API

### Phase 1: Project Setup
- FastAPI application
- Docker containerization
- Basic UI framework

---

## Breaking Changes

**None** - Fully backwards compatible release.

---

## Configuration Changes

### New Environment Variables

```bash
# Observability
LOG_FORMAT=text  # "text" or "json"

# Admin Authentication (Canonical - Phase 8.1)
ADMIN_AUTH_ENABLED=false
ADMIN_USER=admin
ADMIN_PASSWORD=change_me

# Deprecated (Phase 8.1): BASIC_AUTH_* → AUTO-MAPPED TO ADMIN_AUTH_*

# Demo Mode (Phase 9)
DEMO_MODE=false
DEMO_DB_PATH=data/demo.db
OVERRIDE_DEMO_INGEST=false

# Metrics Authentication (Phase 8)
METRICS_AUTH_ENABLED=false
```

### Migrations

All schema migrations are **idempotent** and run automatically on startup. No manual migration required.

---

## Upgrade Instructions

### From Previous Development Versions

```bash
# 1. Backup current data
docker compose exec -T app python -m app.ops backup

# 2. Pull latest code
git pull origin main

# 3. Update .env (see Configuration Changes above)
cp .env.example .env
nano .env  # Review and update

# 4. Rebuild and restart
docker compose -f docker-compose.prod.yml up -d --build

# 5. Run smoke tests
bash scripts/rc_smoke.sh
```

See `docs/UPGRADE.md` for detailed upgrade and rollback procedures.

---

## Quick Start

### Production Deployment

```bash
# 1. Clone repository
git clone https://github.com/yourusername/vn-bond-lab.git
cd vn-bond-lab

# 2. Configure
cp .env.example .env
nano .env

# 3. Start production
docker compose -f docker-compose.prod.yml up -d --build

# 4. Verify
curl http://localhost:8000/healthz
```

### Demo Mode

```bash
# Seed demo data (180 days)
docker compose run --rm app python -m app.ops seed-demo --days 180

# Enable demo mode
echo "DEMO_MODE=true" >> .env
docker compose restart

# Open browser
open http://localhost:8000
# You'll see: "⚠️ DEMO MODE - Showing synthetic demonstration data"
```

---

## Testing

### Smoke Tests

```bash
# Automated smoke test
bash scripts/rc_smoke.sh

# Manual verification
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
curl http://localhost:8000/api/version | jq
```

### Unit Tests

```bash
# Run all tests
docker compose run --rm app pytest -q

# Run specific test suite
docker compose run --rm app pytest tests/test_observability.py -v
```

---

## Documentation

- **CHANGELOG.md** - Full changelog
- **docs/RUNBOOK_SMOKE.md** - Operator smoke test procedures
- **docs/UPGRADE.md** - Upgrade and rollback guide
- **docs/DEPLOYMENT.md** - Production deployment guide
- **docs/history/PHASE9_SUMMARY.md** - Phase 9 implementation summary

---

## Known Issues

None for RC1.

---

## Next Steps

After RC1 validation:

1. Gather user feedback
2. Address any issues found
3. Prepare for v1.0.0 final release
4. Additional provider integrations
5. Enhanced analytics features

---

## Contributors

See `git log` for full contributor list.

---

## Support

- **Issues**: https://github.com/yourusername/vn-bond-lab/issues
- **Documentation**: See `docs/` directory
- **API Docs**: `http://localhost:8000/docs` (when running)

---

## Download

```bash
# Clone repository
git clone https://github.com/yourusername/vn-bond-lab.git
cd vn-bond-lab

# Checkout RC1 tag
git checkout v1.0.0-rc1

# Deploy
docker compose -f docker-compose.prod.yml up -d --build
```

---

**Thank you for using VN Bond Lab!**
