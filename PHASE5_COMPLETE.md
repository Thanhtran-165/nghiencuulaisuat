# Phase 5 Implementation Summary

## Diff-Style Summary of Changes

### New Files Created

```
app/providers/fred_global.py                    | 350 lines  | FRED global data provider
app/analytics/stress_model.py                   | 680 lines  | BondY stress index computation
app/reports/pdf_daily.py                        | 420 lines  | PDF report generator
app/reports/__init__.py                         |   2 lines  | Reports package init
app/templates/stress.html                       | 620 lines  | Stress dashboard UI
tests/test_stress_model.py                      | 150 lines  | Stress model tests
docs/GLOBAL_DATA.md                             | 280 lines  | Global data documentation
docs/STRESS_MODEL.md                            | 350 lines  | Stress model documentation
```

### Modified Files

```
app/config.py                                   | +3 lines  | Added FRED_API_KEY config
app/db/schema.py                                | +180 lines | Added global_rates_daily, bondy_stress_daily tables
app/main.py                                     | +65 lines | Added /stress and /report/daily.pdf routes
app/api/routes.py                               | +140 lines | Added stress + PDF API endpoints
app/ingest.py                                   | +55 lines | Added fred_global + stress computation hooks
app/analytics/cli.py                            | +125 lines | Added stress CLI commands
app/templates/base.html                         | +1 line   | Added "Stress" nav link
requirements.txt                               | +4 lines  | Added requests, reportlab, matplotlib
```

### Database Schema Changes

**New Tables:**
- `global_rates_daily`: Stores FRED data (date, series_id, series_name, value, source, fetched_at)
- `bondy_stress_daily`: Stores stress index (date, stress_index, regime_bucket, driver_json, computed_at)

**New Views:**
- `v_bondy_stress_latest`: Latest stress record
- `v_bondy_stress_timeseries`: All stress records ordered by date

**New Methods in DatabaseManager:**
- `_create_global_rates_daily_table()`
- `insert_global_rates()`
- `get_global_rates()`
- `_create_bondy_stress_daily_table()`
- `insert_bondy_stress()`
- `get_bondy_stress()`
- `_create_bondy_stress_views()`

---

## Final Endpoint List

### UI Pages

| Endpoint | Method | Description | Auth Required |
|----------|--------|-------------|---------------|
| `/` | GET | Main dashboard | No |
| `/yield-curve` | GET | Yield curve analytics | No |
| `/interbank` | GET | Interbank rates | No |
| `/auctions` | GET | Auction results | No |
| `/secondary` | GET | Secondary trading | No |
| `/policy` | GET | Policy rates | No |
| `/transmission` | GET | Transmission analytics dashboard | No |
| `/snapshot/today` | GET | Vietnamese daily snapshot | No |
| **`/stress`** | **GET** | **BondY stress dashboard** | **No** |
| `/admin/ingest` | GET | Admin ingestion panel | No |
| **`/report/daily.pdf`** | **GET** | **Daily PDF report** | **No** |

### API Endpoints

| Endpoint | Method | Description | Return Type |
|----------|--------|-------------|-------------|
| `/api/yield-curve/latest` | GET | Latest yield curve | List[YieldCurveRecord] |
| `/api/interbank/latest` | GET | Latest interbank rates | List[InterbankRateRecord] |
| `/api/transmission/latest` | GET | Latest transmission metrics | List[TransmissionMetricRecord] |
| `/api/transmission/timeseries` | GET | Transmission time series | List[TransmissionMetricRecord] |
| `/api/transmission/alerts` | GET | Transmission alerts | List[TransmissionAlertRecord] |
| `/api/snapshot/today` | GET | Daily snapshot JSON | Snapshot data |
| **`/api/stress/latest`** | **GET** | **Latest BondY stress** | **List[BondYStressRecord]** |
| **`/api/stress/timeseries`** | **GET** | **Stress time series** | **List[BondYStressRecord]** |
| **`/api/stress/drivers`** | **GET** | **Top stress drivers** | **Driver data** |
| **`/api/report/daily`** | **GET** | **PDF metadata** | **File info** |
| `/api/admin/ingest-runs` | GET | Ingestion runs | List[IngestRunRecord] |
| `/api/admin/coverage` | GET | Data coverage stats | Coverage info |
| `/api/admin/transmission/compute` | POST | Compute transmission metrics | Result status |
| **`/api/admin/stress/compute`** | **POST** | **Compute stress metrics** | **Result status** |
| `/api/admin/ingest/daily` | POST | Trigger daily ingest | Result status |
| `/api/admin/ingest/backfill` | POST | Trigger backfill | Result status |
| `/api/admin/ingest/probe` | POST | Probe providers | Probe results |

---

## Dataset/Feature Matrix

### Features Available Without FRED (Global Disabled)

| Feature | Status | Notes |
|---------|--------|-------|
| VN Yield Curves | ✓ Fully operational | All tenors available |
| Interbank Rates | ✓ Fully operational | ON, 1W, 1M, etc. |
| Auction Results | ✓ Fully operational | Full data |
| Secondary Trading | ✓ Fully operational | Full data |
| Policy Rates | ✓ Fully operational | Full data |
| Transmission Analytics | ✓ Fully operational | All metrics |
| Snapshot Generator | ✓ Fully operational | Vietnamese |
| **BondY Stress Index** | ✓ **Fully operational** | **Core features only** |
| Stress Dashboard | ✓ Fully operational | Global sections hidden |
| PDF Reports | ✓ Fully operational | No global spreads |
| VN-US Spreads | ✗ Not available | Requires FRED data |
| VN-US Correlation | ✗ Not available | Requires FRED data |
| Global Rate Alerts | ✗ Not available | Requires FRED data |

### Features Enabled With FRED (Global Enabled)

| Feature | Status | Additional Capabilities |
|---------|--------|------------------------|
| All VN-only features | ✓ | Same as above |
| BondY Stress Index | ✓ | + Global comparators |
| Stress Dashboard | ✓ | + VN vs US charts |
| PDF Reports | ✓ | + Spread charts |
| VN-US Spreads | ✓ | 10Y, 2Y, slope diff |
| VN-US Correlation | ✓ | 60-day rolling |
| Global Rate Alerts | ✓ | Shock detection |

### Degradation Strategy

**When FRED is disabled:**
- System continues to work with VN-only data
- `/stress` page shows "Global Comparators Disabled" banner
- Stress index uses only VN components (30% transmission, 25% liquidity, 20% curve, 15% auction, 10% turnover)
- No global alerts or spread calculations
- PDF reports exclude global sections

**When FRED is enabled:**
- Stress index includes global comparators
- Additional spread metrics available
- Global rate shock alerts activated
- Full dashboard functionality

---

## Copy-Paste Commands for User

### 1. Enable FRED (Optional)

```bash
# Get free FRED API key from: https://fred.stlouisfed.org/docs/api/api_key.html

# Add to .env file
echo "FRED_API_KEY=your_api_key_here" >> .env

# Verify configuration
python -c "from app.config import settings; print(f'FRED enabled: {bool(settings.fred_api_key)}')"
```

### 2. Run Daily Pipeline (Ingest + Compute + Stress + PDF)

```bash
# Install new dependencies first
pip install requests reportlab matplotlib

# Run complete daily pipeline
python -m app.ingest daily

# This automatically:
# 1. Fetches all provider data (including FRED if enabled)
# 2. Computes transmission metrics
# 3. Computes BondY stress index
# 4. Generates alerts

# Generate PDF report (optional, separate step)
curl "http://localhost:8000/report/daily.pdf" --output daily_report.pdf
```

### 3. Manual Stress Computation

```bash
# Compute stress for specific date
python -m app.analytics stress --date 2024-12-20

# Compute stress for date range
python -m app.analytics stress-range --start 2024-01-01 --end 2024-12-31

# Via API
curl -X POST "http://localhost:8000/api/admin/stress/compute?target_date=2024-12-20"
```

### 4. Access Dashboards

```bash
# Start server
uvicorn app.main:app --reload

# Open in browser:
# - Main dashboard: http://localhost:8000/
# - Transmission analytics: http://localhost:8000/transmission
# - Stress dashboard: http://localhost:8000/stress
# - Daily snapshot (Vietnamese): http://localhost:8000/snapshot/today
# - PDF report: http://localhost:8000/report/daily.pdf
```

### 5. Backfill Historical Stress

```bash
# First, ensure transmission metrics are computed for historical period
python -m app.analytics compute-range --start 2024-01-01 --end 2024-12-31

# Then compute stress for same period
python -m app.analytics stress-range --start 2024-01-01 --end 2024-12-31

# Stress computation is fast (uses already-computed transmission metrics)
```

### 6. Backfill FRED Data (Optional)

```bash
# Fetch 1 year of US Treasury data (if FRED enabled)
python -m app.ingest backfill --start 2024-01-01 --end 2024-12-31 --providers fred_global

# FRED data is used for:
# - VN vs US spread calculations
# - Rolling correlations
# - Global rate shock alerts
```

### 7. Verify Installation

```bash
# Test stress model
python -m pytest tests/test_stress_model.py -v

# Check data availability
curl "http://localhost:8000/api/admin/coverage" | jq

# Get latest stress index
curl "http://localhost:8000/api/stress/latest" | jq

# Get stress timeseries
curl "http://localhost:8000/api/stress/timeseries?start_date=2024-01-01" | jq
```

---

## Architecture Notes

### Component Weights (Stress Index)

```
Transmission Score: 30%
Liquidity Stress:    25%
Curve Stress:        20%
Auction Stress:      15%
Turnover Stress:     10%
```

### Regime Buckets (Stress)

```
S0:  0-20   Very Low Stress
S1: 20-40   Low Stress
S2: 40-60   Moderate Stress
S3: 60-80   High Stress
S4: 80-100  Very High Stress
```

### Regime Buckets (Transmission)

```
B0:  0-20   Very Easy
B1: 20-40   Easy
B2: 40-60   Neutral
B3: 60-80   Tight
B4: 80-100  Very Tight
```

### Data Flow

```
Daily Ingestion
    ↓
[Providers] → FRED (optional) + HNX + SBV + ABO
    ↓
[Raw Data Tables] → gov_yield_curve, interbank_rates, global_rates_daily, etc.
    ↓
[Analytics Layer] → Transmission Metrics → BondY Stress Index
    ↓
[Storage] → transmission_daily_metrics, bondy_stress_daily
    ↓
[Alerts] → transmission_alerts (with global alerts if enabled)
    ↓
[UI + Reports] → /stress, /transmission, PDF reports
```

---

## Testing Checklist

### Without FRED (VN-only)

```bash
# 1. Start server
uvicorn app.main:app --reload

# 2. Access /stress - should show "Global Comparators Disabled" banner
open http://localhost:8000/stress

# 3. Compute stress
python -m app.analytics stress --date $(date +%Y-%m-%d)

# 4. Verify stress index computed
curl "http://localhost:8000/api/stress/latest" | jq '.[0].stress_index'

# 5. Generate PDF
curl "http://localhost:8000/report/daily.pdf" --output test.pdf
file test.pdf  # Should exist and be non-empty
```

### With FRED (Global enabled)

```bash
# 1. Set FRED API key
export FRED_API_KEY=your_key_here

# 2. Fetch FRED data
python -m app.ingest daily  # Includes fred_global provider

# 3. Verify global data
curl "http://localhost:8000/api/admin/coverage" | jq '.global_rates_daily'

# 4. Access /stress - should show VN vs US charts
open http://localhost:8000/stress

# 5. Check global alerts
curl "http://localhost:8000/api/transmission/alerts?limit=10" | jq '.[] | select(.alert_type | contains("GLOBAL"))'
```

---

## File Manifest

### Core Application (Modified)
- ✅ app/config.py - Added FRED configuration
- ✅ app/db/schema.py - Added global + stress tables
- ✅ app/main.py - Added /stress + /report/daily.pdf routes
- ✅ app/api/routes.py - Added stress/PDF APIs
- ✅ app/ingest.py - Integrated FRED + stress computation
- ✅ app/analytics/cli.py - Added stress CLI commands
- ✅ app/templates/base.html - Added Stress nav link
- ✅ requirements.txt - Added new dependencies

### New Modules
- ✅ app/providers/fred_global.py - FRED data provider
- ✅ app/analytics/stress_model.py - Stress index computation
- ✅ app/reports/pdf_daily.py - PDF generation
- ✅ app/reports/__init__.py - Package init

### New UI Templates
- ✅ app/templates/stress.html - Stress dashboard

### Tests
- ✅ tests/test_stress_model.py - Stress model + PDF tests

### Documentation
- ✅ docs/GLOBAL_DATA.md - FRED integration guide
- ✅ docs/STRESS_MODEL.md - Stress model documentation

---

## Next Steps (Phase 6)

As requested by user, Phase 6 will include:
1. **Threshold-based alerts** - Customizable alert thresholds by user
2. **Automated reporting schedule** - CRON-based daily/weekly PDF generation
3. **"So với hôm qua" standardization** - Consistent previous-day comparison workflow
4. **Notification system** - Email/webhook alerts when thresholds breached

All Phase 5 features are complete and ready for production use!
