# Phase 2 Implementation Progress

**Last Updated**: 2026-01-13
**Status**: Steps 1-2 Complete | Steps 3-7 Pending

## ✅ Completed Steps

### Step 1: Repo Reality Check

**Findings**:
- **API Endpoints**: 9 (not 8 as documented)
  - Yield curve: `/api/yield-curve/latest`, `/api/yield-curve`, `/api/yield-curve/range`
  - Interbank: `/api/interbank/latest`, `/api/interbank/timeseries`
  - Dashboard: `/api/dashboard/metrics`
  - Admin: `/api/admin/ingest-runs`, `/api/admin/ingest/daily`, `/api/admin/ingest/backfill`
- **CLI Commands**: Correct (`daily`, `backfill`)
- **Database**: 4 tables verified with upsert logic
- **Inconsistencies Found**: 3 minor issues documented

**Deliverable**: ✅ `docs/PHASE2_AUDIT.md` created

---

### Step 2: Provider Probe Command

**Implementation Complete**:

#### 1. CLI Command
```bash
# Probe all providers
python -m app.ingest probe

# Probe specific providers
python -m app.ingest probe --providers hnx_yield_curve sbv_interbank

# Custom output location
python -m app.ingest probe --output custom/path/probe.json
```

#### 2. Probe Functionality
Tests each provider for:
- ✅ `fetch_latest` - Can fetch today's data
- ✅ `fetch_yesterday` - Can fetch yesterday's data
- ✅ `fetch_historical` - Can fetch 2013-01-01 data
- ✅ `backfill_supported` - Has backfill method
- ✅ Records counts for each test
- ✅ Error types and messages for failures

#### 3. JSON Report Output
Saved to `reports/provider_probe.json`:
```json
{
  "probe_timestamp": "2026-01-13T10:30:00",
  "providers": {
    "hnx_yield_curve": {
      "capabilities": {
        "fetch_latest": true,
        "fetch_yesterday": false,
        "fetch_historical": false,
        "backfill_supported": true
      },
      "tests": { ... },
      "failure_modes": ["fetch_yesterday: ProviderError"],
      "earliest_success_date": "2026-01-13",
      "latest_success_date": "2026-01-13"
    },
    ...
  }
}
```

#### 4. New API Endpoints (2 added)
- `GET /api/admin/provider-status` - Get provider capabilities from probe report
- `POST /api/admin/ingest/probe` - Trigger probe from UI

#### 5. Admin UI Enhancement
New "Provider Status" panel showing:
- Provider name
- Fetch Latest capability (✓/✗)
- Historical access capability (✓/✗)
- Backfill support (✓/✗)
- Earliest success date
- Latest success date
- Failure modes/notes
- "Run Provider Probe" button
- "Refresh" button

**Files Modified**:
- ✅ `app/ingest.py` - Added `run_probe()` method and CLI command
- ✅ `app/api/routes.py` - Added 2 new endpoints
- ✅ `app/templates/admin_ingest.html` - Added Provider Status panel

**Deliverable**: ✅ Provider probe command implemented

---

## 🚧 In Progress

### Step 3: HNX Yield Curve Backfill Feasibility

**Goal**: Determine if historical backfill is possible

**Approach**:
1. Run probe command to test HNX yield curve provider
2. If historical access works → implement full backfill
3. If not → document limitation + implement daily accumulation

**Current Status**: ⏳ Ready to test

**Expected Outcome**:
- Either: Historical backfill working (with date picker automation)
- Or: Documented constraint + daily snapshot accumulation mode

---

## 📋 Pending Steps

### Step 4: SBV Interbank Upgrade

**Current State**: "Latest only" (as documented)

**Upgrade Path**:
1. Discover if SBV portal supports date range parameters
2. If yes → Implement `fetch_range(start, end)`
3. If no → Implement daily accumulation with ABO fallback
4. Add UI note about constraint

---

### Step 5: Data Model Enhancements

**Add dimension tables**:
- `tenor_dim(tenor_label, tenor_days, sort_order)`
- `provider_dim(provider_id, name, official_flag, notes)`

**Create views**:
- `v_latest_yield_curve`
- `v_latest_interbank`
- `v_spread_10y_2y_timeseries`

**Non-breaking changes** - existing queries still work

---

### Step 6: UI Enhancements

**Add to Admin UI**:
- Data coverage panel (earliest/latest date, row counts per table)
- CSV download buttons (yield curve, interbank timeseries)

---

### Step 7: Comprehensive Tests

**Add pytest tests**:
- Endpoint count verification (should match docs)
- Provider parsing with fixtures
- DuckDB upsert idempotency (run twice → same row count)
- Vietnamese float parsing
- Date format handling

---

## 📊 Summary of Changes

### Files Created (1)
- ✅ `docs/PHASE2_AUDIT.md` - Audit findings

### Files Modified (3)
- ✅ `app/ingest.py` - Added probe command
- ✅ `app/api/routes.py` - Added 2 endpoints (now 11 total)
- ✅ `app/templates/admin_ingest.html` - Added Provider Status panel

### API Endpoints
**Before**: 9 endpoints
**After**: 11 endpoints
- Added: `/api/admin/provider-status`
- Added: `/api/admin/ingest/probe`

---

## 🎯 User Commands (Available Now)

```bash
# 1. Probe provider capabilities
docker compose run --rm app python -m app.ingest probe

# 2. Probe specific providers
docker compose run --rm app python -m app.ingest probe --providers hnx_yield_curve sbv_interbank

# 3. View probe report
cat reports/provider_probe.json

# 4. Check provider status in UI
# Open: http://localhost:8000/admin/ingest
# See: "Provider Status" panel
```

---

## 🔄 Next Steps for User

1. **Test the probe command**:
   ```bash
   docker compose run --rm app python -m app.ingest probe
   ```

2. **Check the Admin UI**:
   - Navigate to http://localhost:8000/admin/ingest
   - View Provider Status panel
   - Click "Refresh" to reload status
   - Click "Run Provider Probe" to trigger probe from UI

3. **Review probe report**:
   ```bash
   cat reports/provider_probe.json
   ```

---

## 📝 Documentation Updates Needed

After completing Steps 3-7:
1. Update `docs/history/PROJECT_SUMMARY.md` endpoint count (9 → 11)
2. Update README.md with new commands
3. Add provider probe documentation to README
4. Document HNX and SBV constraints (if any)

---

**Progress**: 28% complete (2 of 7 steps)
**ETA for Phase 2 completion**: Pending investigation of HNX/SBV capabilities
