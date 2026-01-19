# Phase 3: Expand Dataset Coverage - COMPLETION REPORT

**Status**: ✅ CORE INFRASTRUCTURE COMPLETE | 📋 TEMPLATES PROVIDED
**Date**: 2026-01-13

---

## (1) DIFF-STYLE SUMMARY: FILES CHANGED

### Created Files (3)
```
app/dataset_catalog.py           - Dataset catalog CLI (+200 lines)
docs/DATASET_CATALOG.md          - Dataset documentation
PHASE3_COMPLETE.md              - This file
```

### Modified Files (4)
```
app/db/schema.py                 (+160 lines) - Added 3 new tables
app/ingest.py                    (+25 lines)  - Added 'catalog' command
app/api/routes.py                (see below)  - API endpoints
app/main.py                     (see below)  - Routes + templates
```

### New Database Tables (3)
```
gov_auction_results              - Primary market auction results
gov_secondary_trading           - Secondary market trading stats
policy_rates                    - SBV policy rates
```

---

## (2) FINAL API ENDPOINT LIST (21 endpoints)

### Core Data (6)
1.  GET /api/yield-curve/latest
2.  GET /api/yield-curve
3.  GET /api/yield-curve/range
4.  GET /api/interbank/latest
5.  GET /api/interbank/timeseries
6.  GET /api/dashboard/metrics

### Admin & Ingest (6)
7.  GET /api/admin/ingest-runs
8.  POST /api/admin/ingest/daily
9.  POST /api/admin/ingest/backfill
10. GET /api/admin/provider-status
11. GET /api/admin/coverage
12. POST /api/admin/ingest/probe

### Export (3)
13. GET /api/export/yield-curve.csv
14. GET /api/export/interbank.csv
15. GET /api/export/auctions.csv (TEMPLATE)

### New Datasets (3) - TEMPLATE ENDPOINTS
16. GET /api/auctions/latest (TEMPLATE)
17. GET /api/secondary/latest (TEMPLATE)
18. GET /api/policy-rates/latest (TEMPLATE)

### Data Catalog (1)
19. GET /api/catalog (NEW - lists all datasets)

### Export New Datasets (3)
20. GET /api/export/secondary.csv (TEMPLATE)
21. GET /api/export/policy-rates.csv (TEMPLATE)

**Note**: Endpoints marked "TEMPLATE" have schema defined but need provider implementation.

---

## (3) DATASET MATRIX: HISTORICAL ACCESS + PROVENANCE

| Dataset ID | Historical | Earliest | Latest | Provenance | Strategy | Command |
|------------|-----------|----------|--------|------------|----------|---------|
| **gov_yield_curve** | ❌ NO | Today | Today | OFFICIAL (HNX) | Daily accumulation | `python -m app.ingest daily` |
| **gov_yield_change_stats** | ✅ YES | 2013-01-01 | Today | OFFICIAL (HNX FTP) | Backfill | `python -m app.ingest backfill --start 2013-01-01 --end today --providers hnx_ftp_pdf` |
| **interbank_rates** | ❌ NO | Today | Today | OFFICIAL (SBV) | Daily accumulation | `python -m app.ingest daily` |
| **gov_auction_results** | 🔍 TEMPLATE | 2013-01-01 | Today | OFFICIAL (HNX) | Backfill (needs provider) | `TODO: Implement HNXAuctionProvider` |
| **gov_secondary_trading** | 🔍 TEMPLATE | 2013-01-01 | Today | OFFICIAL (HNX) | Backfill (needs provider) | `TODO: Implement HNXTradingProvider` |
| **policy_rates** | 🔍 TEMPLATE | Today | Today | OFFICIAL (SBV) | Daily accumulation (needs provider) | `TODO: Implement SBVPolicyProvider` |

**Legend**:
- ❌ NO = Latest only, daily accumulation required
- ✅ YES = Full historical backfill supported
- 🔍 TEMPLATE = Database + API ready, provider needs implementation

---

## (4) NON-PROGRAMMER COMMANDS

### Command 1: View Dataset Catalog
```bash
cd "vn-bond-lab"

# Show catalog as table
docker compose run --rm app python -m app.ingest catalog

# Export as JSON
docker compose run --rm app python -m app.ingest catalog --format json --output reports/dataset_catalog.json

# View JSON
cat reports/dataset_catalog.json | python -m json.tool
```

**What it shows**:
- All available datasets
- Which support historical backfill
- Earliest known dates
- Provider names
- Provenance (OFFICIAL/NON-OFFICIAL)

---

### Command 2: Safe Backfill (Historical Datasets Only)
```bash
# HNX FTP PDF (yield change statistics) - FULLY IMPLEMENTED
# Test with 3 months first
docker compose run --rm app python -m app.ingest backfill \
  --start 2020-01-01 \
  --end 2020-03-31 \
  --providers hnx_ftp_pdf

# If successful, backfill full range
docker compose run --rm app python -m app.ingest backfill \
  --start 2013-01-01 \
  --end 2023-12-31 \
  --providers hnx_ftp_pdf
```

**DO NOT backfill**: hnx_yield_curve, sbv_interbank (they will error with NotSupportedError)

---

### Command 3: Start Daily Accumulation (Latest-Only Datasets)
```bash
# Run daily ingestion (fetches latest from ALL providers)
docker compose run --rm app python -m app.ingest daily

# Enable automatic daily updates (runs every day at 18:05)
# Edit .env file:
echo "SCHEDULER_ENABLED=true" >> .env

# Restart to apply
docker compose restart

# Check logs
docker compose logs -f
```

**What accumulates**:
- ✅ HNX Yield Curve (from start date)
- ✅ SBV Interbank Rates (from start date)
- ✅ HNX FTP PDF Statistics (from start date)

**Result**: After 6 months, you'll have ~180 daily snapshots of yield curves and interbank rates.

---

### Command 4: Check Coverage
```bash
# Open Admin UI
open http://localhost:8000/admin/ingest

# Check panels:
# - "Provider Status": Shows which providers work
# - "Recent Ingestion Runs": Shows what data was collected
# - "Data Coverage": Shows earliest/latest dates per table
```

---

## IMPLEMENTATION STATUS

### ✅ FULLY IMPLEMENTED (Working Now)

1. **Dataset Catalog CLI**
   - Command: `python -m app.ingest catalog`
   - Lists all datasets with metadata
   - JSON export available

2. **Database Schema**
   - 3 new tables created automatically
   - Indexes for performance
   - Upsert logic for idempotency

3. **HNX FTP PDF Provider**
   - Full historical backfill from 2013
   - Parse yield change statistics
   - Working and tested

4. **HNX Yield Curve Provider**
   - Latest-only (truthful with NotSupportedError)
   - Daily accumulation
   - Capability flags

5. **SBV Interbank Provider**
   - Latest-only (truthful with NotSupportedError)
   - Daily accumulation
   - Capability flags

6. **Admin UI**
   - Provider Status panel
   - Recent Ingestion Runs
   - Data Coverage panel (earliest/latest dates)

7. **CSV Export**
   - Yield curve export
   - Interbank rates export
   - Downloadable from UI or API

### 🔧 TEMPLATE IMPLEMENTED (Schema + API Ready, Provider Needed)

8. **Government Auction Results**
   - ✅ Database table: `gov_auction_results`
   - ✅ API endpoint template: `/api/auctions/latest`
   - ✅ CSV export template: `/api/export/auctions.csv`
   - ⏳ Provider needed: `HNXAuctionProvider`
   - **Pattern to follow**: HNX FTP PDF provider

9. **Secondary Market Trading**
   - ✅ Database table: `gov_secondary_trading`
   - ✅ API endpoint template: `/api/secondary/latest`
   - ✅ CSV export template: `/api/export/secondary.csv`
   - ⏳ Provider needed: `HNXTradingProvider`
   - **Pattern to follow**: HNX FTP PDF provider

10. **Policy Rates**
    - ✅ Database table: `policy_rates`
    - ✅ API endpoint template: `/api/policy-rates/latest`
    - ✅ CSV export template: `/api/export/policy-rates.csv`
    - ⏳ Provider needed: `SBVPolicyProvider`
    - **Pattern to follow**: SBV Interbank provider

---

## EXTENDING TO NEW DATASETS (Implementation Guide)

To add a new dataset (e.g., auction results), follow this pattern:

### Step 1: Create Provider
```python
# app/providers/hnx_auction.py

from app.providers.base import BaseProvider

class HNXAuctionProvider(BaseProvider):
    def __init__(self):
        super().__init__()
        self.auction_url = "https://hnx.vn/trai-phieu/dau-gia-trai-phieu.html"
        self.supports_historical = True  # Change if False

    def fetch(self, target_date: date) -> List[Dict]:
        # Scrape or download auction results for target_date
        # Return list of records matching gov_auction_results schema
        pass

    def backfill(self, start_date: date, end_date: date) -> List[Dict]:
        # Iterate through dates and call fetch()
        # OR raise NotSupportedError if latest-only
        pass
```

### Step 2: Register in Ingestion Pipeline
```python
# app/ingest.py - IngestionPipeline.PROVIDERS

PROVIDERS = {
    'hnx_yield_curve': HNXYieldCurveProvider,
    'hnx_ftp_pdf': HNXFTPPDFProvider,
    'sbv_interbank': SBVInterbankProvider,
    'abo': ABOMarketWatchProvider,
    'hnx_auction': HNXAuctionProvider,  # Add this
}
```

### Step 3: Add Insert Method to Database
```python
# app/db/schema.py - DatabaseManager

def insert_auction_results(self, records: list[dict]) -> int:
    sql = """
    INSERT INTO gov_auction_results (
        date, instrument_type, tenor_label, tenor_days,
        amount_offered, amount_sold, bid_to_cover, cut_off_yield,
        avg_yield, source, raw_file, fetched_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (date, instrument_type, tenor_label, source)
    DO UPDATE SET
        amount_offered = EXCLUDED.amount_offered,
        amount_sold = EXCLUDED.amount_sold,
        ...
    """
    self.con.executemany(sql, records)
    return len(records)
```

### Step 4: Add API Endpoints
```python
# app/api/routes.py

@router.get("/api/auctions/latest")
async def get_latest_auctions():
    records = db_manager.con.execute("SELECT * FROM gov_auction_results ORDER BY date DESC LIMIT 100").fetchall()
    # Convert to response models
    pass

@router.get("/api/export/auctions.csv")
async def export_auctions_csv(start_date: str, end_date: str):
    # Query data and return as CSV
    pass
```

### Step 5: Add UI Page
```python
# app/templates/auctions.html
# Follow pattern from yield_curve.html
```

### Step 6: Update Dataset Catalog
```python
# app/dataset_catalog.py

DATASET_CATALOG["gov_auction_results"] = {
    "name": "Government Bond Auction Results",
    "provider": "HNX_AUCTION",
    "supports_historical": True,
    "earliest_known_date": "2013-01-01",
    ...
}
```

---

## ACCUMULATION STRATEGY SUMMARY

### For Historical Datasets (Backfill Supported)
**HNX FTP PDF (Yield Change Statistics)**:
```bash
docker compose run --rm app python -m app.ingest backfill \
  --start 2013-01-01 \
  --end 2023-12-31 \
  --providers hnx_ftp_pdf
```

**Result**: Full historical data from 2013 onwards

---

### For Latest-Only Datasets (Daily Accumulation)

**HNX Yield Curve** + **SBV Interbank**:
```bash
# Start accumulating from today
docker compose run --rm app python -m app.ingest daily

# Enable automatic daily updates
echo "SCHEDULER_ENABLED=true" >> .env
docker compose restart
```

**Result**: Daily snapshots accumulate over time
- After 1 month: ~30 records
- After 6 months: ~180 records
- After 1 year: ~365 records

---

## PHASE 3 DELIVERABLES CHECKLIST

### ✅ Completed

- [x] Dataset catalog CLI command
- [x] Database schema for 3 new datasets
- [x] API endpoint structure (templates provided)
- [x] CSV export endpoints (templates provided)
- [x] Documentation for dataset catalog
- [x] HNX FTP PDF full implementation (historical)
- [x] HNX Yield Curve implementation (latest-only)
- [x] SBV Interbank implementation (latest-only)
- [x] Truthful provider capabilities (NotSupportedError)
- [x] Admin UI with coverage panels

### 🔧 Templates Provided (Ready for Implementation)

- [x] Database schema for auctions
- [x] Database schema for secondary trading
- [x] Database schema for policy rates
- [x] API endpoint templates for new datasets
- [x] CSV export templates for new datasets
- [x] Implementation guide (see above)

### ⏳ Requires Implementation

- [ ] HNXAuctionProvider (scrape auction results)
- [ ] HNXTradingProvider (scrape trading stats)
- [ ] SBVPolicyProvider (scrape policy rates)
- [ ] UI pages: /auctions, /secondary, /policy
- [ ] Tests for new providers
- [ ] Fixtures for new providers

---

## NEXT STEPS FOR USER

### Immediate (What You Can Do Now)

1. **Run catalog to see all datasets**:
   ```bash
   docker compose run --rm app python -m app.ingest catalog
   ```

2. **Backfill HNX FTP PDF (historical)**:
   ```bash
   docker compose run --rm app python -m app.ingest backfill \
     --start 2020-01-01 \
     --end 2020-12-31 \
     --providers hnx_ftp_pdf
   ```

3. **Start daily accumulation**:
   ```bash
   docker compose run --rm app python -m app.ingest daily
   echo "SCHEDULER_ENABLED=true" >> .env
   docker compose restart
   ```

4. **Check coverage in Admin UI**:
   ```bash
   open http://localhost:8000/admin/ingest
   ```

### To Add New Datasets (Future Work)

Follow the implementation guide in the "EXTENDING TO NEW DATASETS" section above.

**Priority Order**:
1. Auction results (HNX_AUCTION provider)
2. Secondary trading (HNX_TRADING provider)
3. Policy rates (SBV_POLICY provider)

Each one follows the same pattern as HNX FTP PDF provider.

---

## FINAL VERDICT

**Working Now** (Immediately usable):
- ✅ Yield Curve (latest, accumulates daily)
- ✅ Yield Change Stats (historical backfill from 2013)
- ✅ Interbank Rates (latest, accumulates daily)
- ✅ Dataset catalog with metadata

**Ready to Extend** (Schema + API done, provider needed):
- 🔧 Auction results
- 🔧 Secondary trading
- 🔧 Policy rates

**Historical Access**:
- **HNX Yield Curve**: NO (daily accumulation from start date)
- **SBV Interbank**: NO (daily accumulation from start date)
- **HNX FTP PDF**: YES (backfill from 2013)

---

**PHASE 3 STATUS**: ✅ CORE COMPLETE | 🔧 EXTENSIBLE
**READY FOR**: Daily accumulation + HNX FTP backfill
**PATTERN ESTABLISHED**: Clear path for adding new datasets
