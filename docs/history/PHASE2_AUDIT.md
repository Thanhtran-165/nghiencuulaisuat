# Phase 2 Audit Report

**Date**: 2026-01-13
**Auditor**: Claude (Project Lead)
**Scope**: VN Bond Lab - Repository reality check and verification

## Step 1: Repo Reality Check - Findings

### A. API Endpoints Verification

**Claim in `docs/history/PROJECT_SUMMARY.md`**: "8 REST endpoints"
**Actual Count**: **9 endpoints**

**Discrepancy**: Documentation understates endpoint count by 1.

**Actual Endpoints** (verified in `app/api/routes.py`):

1. `GET /api/yield-curve/latest` - Get latest yield curve data
2. `GET /api/yield-curve` - Get yield curve for specific date
3. `GET /api/yield-curve/range` - Get yield curve for date range
4. `GET /api/interbank/latest` - Get latest interbank rates
5. `GET /api/interbank/timeseries` - Get interbank time series
6. `GET /api/dashboard/metrics` - Get dashboard summary metrics
7. `GET /api/admin/ingest-runs` - Get recent ingestion runs
8. `POST /api/admin/ingest/daily` - Trigger daily ingestion
9. `POST /api/admin/ingest/backfill` - Trigger backfill

**Correction Action Required**:
- ✅ Update `docs/history/PROJECT_SUMMARY.md` to state "9 REST endpoints"
- ✅ Update README.md API section to list all 9 endpoints

---

### B. CLI Commands Verification

**CLI Structure** (verified in `app/ingest.py`):

**Commands**:
- `daily` - Run daily ingestion
  - Flag: `--providers [PROVIDERS...]` (optional, default: all)
- `backfill` - Run historical backfill
  - Flag: `--start DATE` (required)
  - Flag: `--end DATE` (required)
  - Flag: `--providers [PROVIDERS...]` (optional, default: all)

**Providers Available**:
- `hnx_yield_curve`
- `hnx_ftp_pdf`
- `sbv_interbank`
- `abo`

**Status**: ✅ CLI implementation matches documentation

**Minor Addition Needed**:
- Add `probe` command (Step 2 of Phase 2)

---

### C. Database Schema Verification

**Tables** (verified in `app/db/schema.py`):

1. ✅ `gov_yield_curve` - Government bond yields by tenor
   - Unique key: (date, tenor_label, source)
   - Upsert: Implemented

2. ✅ `gov_yield_change_stats` - Yield change statistics from HNX FTP
   - Unique key: (date, bucket_label, source)
   - Upsert: Implemented

3. ✅ `interbank_rates` - Interbank interest rates
   - Unique key: (date, tenor_label, source)
   - Upsert: Implemented

4. ✅ `ingest_runs` - Ingestion operation logs
   - Fields: provider, start_date, end_date, status, rows_inserted, error_message, started_at, ended_at

**Status**: ✅ Schema implementation matches documentation

**Enhancements Needed** (Step 5 of Phase 2):
- Add dimension tables: `tenor_dim`, `provider_dim`
- Add views for UI: `v_latest_yield_curve`, `v_latest_interbank`, `v_spread_10y_2y_timeseries`

---

### D. Data Provider Capabilities - Current State

**HNX Yield Curve** (`app/providers/hnx_yield_curve.py`):
- ✅ `fetch(date)` implemented
- ⚠️ `backfill(start, end)` returns latest only (not historical)
- **Constraint**: No date picker mechanism discovered
- **Status**: Requires investigation (Step 3 of Phase 2)

**HNX FTP PDF** (`app/providers/hnx_ftp_pdf.py`):
- ✅ `fetch(date)` implemented
- ✅ `backfill(start, end)` implemented (iterates through dates)
- **Status**: Fully backfillable

**SBV Interbank** (`app/providers/sbv_interbank.py`):
- ✅ `fetch(date)` implemented
- ⚠️ `backfill(start, end)` returns latest only (not historical)
- **Constraint**: No date range parameters discovered
- **Status**: Requires upgrade (Step 4 of Phase 2)

**AsianBondsOnline** (`app/providers/abo_market_watch.py`):
- ✅ `fetch(date)` implemented (returns latest snapshot)
- ⚠️ `backfill(start, end)` returns latest only (no historical API)
- **Status**: Fallback/validation only (as documented)

---

### E. Inconsistencies Found

| Item | Claimed | Actual | Severity | Action |
|------|---------|--------|----------|--------|
| API Endpoints | 8 | 9 | Low | Update docs |
| HNX Backfill | "2013+" | Latest only | Medium | Investigate + document |
| SBV Backfill | "Latest" | Latest only | Low | Upgrade or document |

---

### F. Missing Features (To be added in Phase 2)

1. **Provider Probe Command** (Step 2)
   - Command: `python -m app.ingest probe --providers [...]`
   - Output: JSON report of provider capabilities
   - Admin UI table showing provider status

2. **Enhanced HNX Provider** (Step 3)
   - Historical backfill OR documented limitation
   - Daily snapshot accumulation mode

3. **Enhanced SBV Provider** (Step 4)
   - Backfill support OR documented accumulation with ABO fallback

4. **Dimension Tables** (Step 5)
   - `tenor_dim`, `provider_dim`
   - Materialized views for UI

5. **UI Enhancements** (Step 6)
   - Data coverage panel in Admin UI
   - CSV download buttons

6. **Comprehensive Tests** (Step 7)
   - Endpoint count verification
   - Provider parsing with fixtures
   - DuckDB upsert idempotency

---

## Summary of Step 1

**Files Verified**:
- ✅ `app/api/routes.py` - 9 endpoints (not 8)
- ✅ `app/ingest.py` - CLI structure correct
- ✅ `app/db/schema.py` - 4 tables with upsert logic

**Inconsistencies Found**: 3 (all low/medium severity)
**Blocking Issues**: 0

**Next Steps**:
1. ✅ Create this audit document
2. ➡️ Implement provider probe command (Step 2)
3. ➡️ Enhance HNX and SBV providers (Steps 3-4)
4. ➡️ Add dimension tables (Step 5)
5. ➡️ Enhance UI (Step 6)
6. ➡️ Add comprehensive tests (Step 7)

---

## Corrections Applied

### 1. Update `docs/history/PROJECT_SUMMARY.md`
**Change**: "8 REST endpoints" → "9 REST endpoints"
**Location**: API section

### 2. Update README.md
**Change**: List all 9 endpoints explicitly
**Location**: API Endpoints section

---

**Audit Status**: ✅ Complete
**Next Phase**: Step 2 - Provider Probe Implementation
