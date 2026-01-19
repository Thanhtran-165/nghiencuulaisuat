# Implementation Plan: Multi-Source Scraping & Automation

## 📊 OVERVIEW

This document outlines the complete implementation plan for adding new data sources and automation to the interest rate scraping system.

**Status**: 🟡 IN PROGRESS (Foundation complete, remaining tasks require R&D)

---

## ✅ COMPLETED TASKS

### 1. Source Registry Foundation
**File**: `app/source_registry.py` ✅

- Created centralized `SourceConfig` dataclass
- Implemented registry with existing Timo sources
- Added helper functions: `get_source()`, `get_sources_by_kind()`, `get_all_source_ids()`
- Parser registry decorator system for extensibility

### 2. Job Runner Script
**File**: `scripts/run_scrape_job.py` ✅

- Production-friendly Python script with CLI arguments
- Logging to `logs/scrape_YYYYMMDD.log` with daily rotation
- Supports `--all`, `--source`, `--kind` flags
- Passes through exit codes (0/2/3) for monitoring
- Compatible with cron and launchd scheduling

### 3. Documentation
**File**: `docs/jobs.md` ✅

- Complete usage guide for job runner
- Cron and launchd configuration examples
- Monitoring and troubleshooting tips

---

## 🔄 PENDING TASKS

### A. ADD NEW DATA SOURCES (Est. 4-6 hours)

#### A2. Research & Select New Sources (1-2 hours)

**Requirements**:
- 2 new deposit sources
- 2 new loan sources
- Must have HTML tables or structured data
- Must NOT require Selenium/Playwright

**Candidate Websites to Research**:

**Deposit Sources:**
1. https://webvaynhanh.vn/bang-lai-suat/ (VietBank comparison)
2. https://ib.com.vn/ky-quan-lai-suat/ (Indovina Bank)
3. https://www.vietcombank.com/iib-v2/Lai-suatgui-tiet-kiem (Vietcombank official)
4. Bank landing pages (BIDV, Agribank, MB, Techcombank)

**Loan Sources:**
1. https://webvaynhanh.vn/bang-lai-suat-vay-tin-chap/ (VietBank)
2. https://www.vpbank.com.vn/lai-suat-vay-dung-tin-chap/ (VPBank)
3. https://www.techcombank.com.vn/lai-suat-vay-tin-chap/ (Techcombank)

**Action Items**:
- [ ] Visit each URL and inspect HTML structure
- [ ] Check if tables are parseable with existing strategy
- [ ] Identify bank list format (table vs names in text)
- [ ] Document rate format (single, min-max, "Từ X")
- [ ] Select top 2 deposit + 2 loan sources based on quality

**Deliverable**: `docs/source_research.md` with findings

#### A3. Create Parsers for New Sources (2-3 hours)

For each new source:

1. **Create parser module**: `app/parsers/deposit_<source_id>.py` or `app/parsers/loan_<source_id>.py`
2. **Implement Strategy A (Table/Header)**:
   - Scope main content (avoid menu/footer)
   - Parse table headers (Vietnamese → field mapping)
   - Extract rates (handle min/max/"Từ X" formats)
3. **Implement Strategy B (Regex/Keyword)**:
   - Find bank names with regex
   - Extract terms and rates with patterns
   - Fallback logic when Strategy A fails
4. **Test with fixtures**: Ensure output matches canonical format
5. **Register in `app/source_registry.py`**: Add new `SourceConfig` entries

**Action Items**:
- [ ] Create parser for deposit source #1
- [ ] Create parser for deposit source #2
- [ ] Create parser for loan source #1
- [ ] Create parser for loan source #2
- [ ] Update source_registry.py with new sources

#### A4. Create Fixtures & Tests (1-2 hours)

For each new source:

1. **Save HTML fixture**:
   ```bash
   curl -s "https://example.com/rates" > tests/fixtures/<source_id>.html
   ```

2. **Create test file**: `tests/test_<source_id>.py`
   ```python
   def test_strategy_a_success_or_fallback():
       # Test parser on fixture
       pass

   def test_term_parsing():
       # Test term extraction (deposit only)
       pass

   def test_rate_parsing():
       # Test min/max/"Từ X" formats
       pass

   def test_scoping():
       # Test menu/footer exclusion
       pass
   ```

3. **Run tests**:
   ```bash
   pytest tests/test_<source_id>.py -v
   ```

**Action Items**:
- [ ] Download fixtures for 4 new sources
- [ ] Create pytest test files for all 4 sources
- [ ] Run and verify all tests pass

---

### B. AUTOMATION SYSTEM (Est. 3-4 hours)

#### B2. Add Run History Table (30 minutes)

**Update**: `app/db.py`

Add new table to schema:

```sql
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('success', 'anomaly', 'fatal')),
    exit_code INTEGER,
    total_sources INTEGER,
    total_extracted INTEGER,
    total_inserted INTEGER
);
```

**Action Items**:
- [ ] Add `scrape_runs` table to schema
- [ ] Create `init_scrape_run()` function
- [ ] Create `finish_scrape_run()` function
- [ ] Update scraper CLI to record run metrics

#### B3. Add FastAPI Status Endpoint (1 hour)

**Update**: `backend/app/main.py`

Add endpoint:

```python
@app.get("/status")
def get_status():
    """
    Get last scrape run status.

    Returns:
        {
            last_run: {
                started_at: "2026-01-05T10:00:00",
                finished_at: "2026-01-05T10:05:00",
                status: "success",
                exit_code: 0
            },
            per_source: [
                {
                    source_id: "timo_deposit",
                    last_scrape_at: "2026-01-05T10:00:00",
                    last_extracted_count: 441,
                    last_strategy_used: "table_header"
                },
                ...
            ]
        }
    """
    # Query scrape_runs table
    # Query sources for per-source metrics
    pass
```

**Action Items**:
- [ ] Add `/status` endpoint to FastAPI
- [ ] Query `scrape_runs` for last run
- [ ] Query `sources` table for per-source metrics
- [ ] Add response schema in `schemas.py`

#### B4. Frontend Status Display (1 hour)

**Update**: `frontend/src/app/page.tsx`

Add status section above KPI cards:

```tsx
{/* Scrape Status */}
<div className="mb-6">
  <GlassCard>
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm text-white/60">Trạng thái cập nhật</p>
        <p className="text-lg font-semibold text-white">
          Cập nhật lần cuối: {formatDate(lastRunTime)}
        </p>
      </div>
      <div className={`px-4 py-2 rounded-lg ${
        status === 'success' ? 'bg-green-500/20 text-green-400' :
        status === 'anomaly' ? 'bg-yellow-500/20 text-yellow-400' :
        'bg-red-500/20 text-red-400'
      }`}>
        {status === 'success' ? '✓ OK' :
         status === 'anomaly' ? '⚠ Cảnh báo' : '✗ Lỗi'}
      </div>
    </div>
    {perSourceMetrics && (
      <details className="mt-4">
        <summary className="text-sm text-white/70 cursor-pointer">
          Chi tiết từng nguồn
        </summary>
        <div className="mt-2 space-y-2">
          {perSourceMetrics.map((source) => (
            <div key={source.source_id} className="text-sm text-white/80">
              {source.source_id}: {formatDate(source.last_scrape_at)} - {source.last_extracted_count} records
            </div>
          ))}
        </div>
      </details>
    )}
  </GlassCard>
</div>
```

**Action Items**:
- [ ] Fetch `/status` on page load
- [ ] Display last run time and status badge
- [ ] Add per-source metrics in collapsible details
- [ ] Handle loading/error states

#### B5. Scheduler Setup (30 minutes)

**Choose ONE option**:

**Option 1: Cron (Recommended - Simple)**

Create example cron config: `scripts/install_cron_example.sh`

```bash
#!/bin/bash
# Example cron installation script
# REVIEW BEFORE RUNNING!

CRON_JOB="0 */6 * * * cd $(pwd) && python scripts/run_scrape_job.py --all >> logs/cron.log 2>&1"

echo "Would add to crontab:"
echo "$CRON_JOB"
echo ""
echo "To install manually, run:"
echo "  crontab -e"
echo "  # Add this line:"
echo "  $CRON_JOB"
```

**Option 2: APScheduler (Optional - Advanced)**

Add to `backend/app/main.py`:

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

@scheduler.scheduled_job('interval', hours=6)
def scheduled_scrape():
    subprocess.run(['python', 'scripts/run_scrape_job.py', '--all'])

scheduler.start()
```

**Action Items**:
- [ ] Choose between cron or APScheduler
- [ ] Create cron example script OR implement APScheduler
- [ ] Test scheduler manually
- [ ] Document setup in README

---

### C. VERIFICATION (30 minutes)

#### C1. Unit Tests
```bash
cd /path/to/Lai_suat
pytest -q
```

Expected: All tests pass, including new source tests

#### C2. Manual E2E Test

```bash
# 1. Fresh database
rm data/rates.db
python -m app.cli init-db

# 2. Scrape all sources
python scripts/run_scrape_job.py --all

# 3. Check status endpoint
curl http://localhost:8001/status

# 4. Check frontend
open http://localhost:3001
# Verify status badge displays correctly
```

#### C3. Anomaly Simulation

```bash
# Temporarily reduce threshold
python scripts/run_scrape_job.py --all --anomaly-threshold 0.05

# Expected: Exit code 2, anomaly logged
```

---

## 📋 ACTION CHECKLIST

### Phase 1: Add New Sources
- [ ] Research and select 2 deposit + 2 loan sources
- [ ] Document findings in `docs/source_research.md`
- [ ] Create parsers for all 4 new sources
- [ ] Download HTML fixtures
- [ ] Write pytest tests for all 4 sources
- [ ] Update `source_registry.py` with new sources
- [ ] Run `pytest` - verify all tests pass

### Phase 2: Automation
- [ ] Add `scrape_runs` table to database schema
- [ ] Update scraper CLI to record runs
- [ ] Add `/status` endpoint to FastAPI
- [ ] Add status display to frontend homepage
- [ ] Choose and implement scheduler (cron OR APScheduler)
- [ ] Document scheduler setup in README

### Phase 3: Verification
- [ ] Run unit tests: `pytest -q`
- [ ] Run E2E test: init-db → scrape → check status
- [ ] Simulate anomaly and verify exit code 2
- [ ] Test scheduler manually
- [ ] Verify frontend status display

---

## 🚧 RISKS & MITIGATION

### Risk 1: New Sources May Not Have Tables
**Mitigation**: Strategy B regex/keyword fallback is required for all sources

### Risk 2: HTML Structure Changes
**Mitigation**: Version parsers, monitor for failures, update fixtures quarterly

### Risk 3: Scheduler Conflicts
**Mitigation**: Use file locking or database locks to prevent concurrent runs

### Risk 4: Performance Impact
**Mitigation**: Scrape job runs in background, frontend caches status responses

---

## 📈 ESTIMATED TIMELINE

- **Research & Selection**: 1-2 hours
- **Parser Development**: 2-3 hours
- **Testing & Fixtures**: 1-2 hours
- **Automation Implementation**: 2-3 hours
- **Verification & Documentation**: 1 hour

**Total**: 7-11 hours

---

## 🎯 NEXT IMMEDIATE STEPS

1. **Research** (Can start immediately):
   - Visit candidate websites
   - Inspect HTML structure
   - Select best 2 deposit + 2 loan sources

2. **Parser Development** (After research):
   - Create parser modules
   - Test with fixtures
   - Register in source_registry

3. **Integration** (After parsers ready):
   - Update database schema
   - Add API endpoint
   - Update frontend

4. **Testing & Deployment**:
   - Run all tests
   - Setup scheduler
   - Monitor first few runs

---

## 📞 SUPPORT

For questions or blockers during implementation:
- Review existing parsers in `app/parsers/deposit.py` and `app/parsers/loan.py`
- Check test files in `tests/` for examples
- Refer to `docs/jobs.md` for scheduler configuration
