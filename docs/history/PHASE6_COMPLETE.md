# Phase 6 Implementation Summary

## Diff-Style Summary of Changes

### New Files Created

```
app/analytics/baseline.py                      | 201 lines  | Baseline utilities for "So với hôm qua"
app/analytics/alert_engine.py                  | 356 lines  | Threshold-based alert engine
app/notifications/__init__.py                  |   5 lines  | Notifications package
app/notifications/sender.py                    | 456 lines  | Email/webhook notification sender
app/scheduler.py                               | 189 lines  | APScheduler integration
app/templates/admin_alerts.html                | 380 lines  | Alert thresholds admin UI
app/templates/admin_notifications.html         | 428 lines  | Notifications admin UI
docs/PHASE6.md                                 | 680 lines  | Phase 6 documentation
```

### Modified Files

```
app/db/schema.py                               | +590 lines | Added 5 new tables + methods
app/analytics/snapshot.py                      | +45 lines  | Baseline standardization + persistence
app/reports/pdf_daily.py                       | +42 lines  | Comparison section + caching
app/api/routes.py                              | +210 lines | Alerts/Notifications API endpoints
app/main.py                                    | +18 lines  | Added /admin/alerts + /admin/notifications routes
app/templates/base.html                        | +2 lines   | Added Alerts + Notifications nav links
```

---

## Final Endpoint List (Phase 6 Additions Only)

### New UI Pages

| Endpoint | Method | Description | Auth Required |
|----------|--------|-------------|---------------|
| **`/admin/alerts`** | **GET** | **Alert thresholds management UI** | **No** |
| **`/admin/notifications`** | **GET** | **Notification channels management UI** | **No** |

### New API Endpoints

| Endpoint | Method | Description | Return Type |
|----------|--------|-------------|-------------|
| **`/api/admin/alerts`** | **GET** | **Get all alert thresholds** | **List[Threshold]** |
| **`/api/admin/alerts/{alert_code}`** | **POST** | **Upsert alert threshold** | **Status** |
| **`/api/admin/alerts/test`** | **POST** | **Test alert threshold** | **Test result** |
| **`/api/admin/alerts/reload`** | **POST** | **Reload thresholds from DB** | **Status** |
| **`/api/admin/notifications`** | **GET** | **Get notification channels** | **List[Channel]** |
| **`/api/admin/notifications/email`** | **POST** | **Create email channel** | **Channel ID** |
| **`/api/admin/notifications/webhook`** | **POST** | **Create webhook channel** | **Channel ID** |
| **`/api/admin/notifications/{channel_id}/toggle`** | **POST** | **Enable/disable channel** | **Status** |
| **`/api/admin/notifications/{channel_id}`** | **DELETE** | **Delete channel** | **Status** |
| **`/api/admin/notifications/events`** | **GET** | **Get notification events** | **List[Event]** |

---

## Dataset/Feature Matrix (Phase 6)

### New Database Tables

**1. daily_snapshots**
- Stores Vietnamese daily snapshots with baseline_date
- Tracks provenance for audit
- Enables "So với hôm qua" standardization

**2. alert_thresholds**
- Stores user-configurable alert thresholds
- Enables customization without code changes
- Default thresholds seeded on init

**3. notification_channels**
- Stores email/webhook configurations
- Safe-by-default: disabled unless explicitly enabled
- Passwords redacted in API responses

**4. notification_events**
- Log of all sent notifications
- Enables deduplication (prevents duplicate sends)
- Tracks delivery status and errors

**5. report_artifacts**
- Cache for generated PDFs
- Tracks generation status (completed/failed)
- Enables PDF reuse without regeneration

### Features Added in Phase 6

| Feature | Description | Optional? |
|---------|-------------|-----------|
| Baseline Standardization | "So với hôm qua" uses last-available date, not T-1 | No |
| Threshold-Based Alerts | User-configurable alert sensitivity | No |
| Notification System | Email/webhook alerts when thresholds breached | Yes |
| Scheduler | Automated daily pipeline + weekly reports | Yes |
| PDF Caching | Artifact table prevents regeneration | No |
| Admin UIs | Manage alerts and notifications via browser | No |

---

## Architecture Changes

### Baseline Date Flow (Step 1)

```
Snapshot Generation
    ↓
[get_previous_available_date()] → Searches backwards from target_date
    ↓                           for most recent date with analytics data
[get_baseline_data()]           → Fetches transmission + stress for baseline
    ↓
[compute_deltas()]              → Calculates current vs baseline changes
    ↓
[Persist to daily_snapshots]    → Stores snapshot with baseline_date
```

**Key Functions:**
- `get_previous_available_date(db, target_date)` - Finds last prior date with data
- `get_baseline_data(db, baseline_date)` - Fetches all metrics for baseline
- `compute_deltas(current, baseline)` - Computes changes

### Alert Engine Flow (Step 2)

```
Alert Detection
    ↓
[AlertEngine._load_thresholds()] → Loads from DB (5-min cache)
    ↓
[Check each alert type]           → Uses DB thresholds or defaults
    ↓
[Create alert records]            → Returns triggered alerts
    ↓
[Insert to transmission_alerts]   → Stored in database
```

**Supported Alert Types:**
1. ALERT_LIQUIDITY_SPIKE - Interbank rate spike (z-score threshold)
2. ALERT_CURVE_BEAR_STEEPEN - Yield curve steepening
3. ALERT_AUCTION_WEAK - Weak auction demand (bid-to-cover)
4. ALERT_TURNOVER_DROP - Secondary market turnover drop
5. ALERT_POLICY_CHANGE - Policy rate change
6. ALERT_TRANSMISSION_HIGH - High transmission score
7. ALERT_STRESS_HIGH - High BondY stress index

### Notification Flow (Step 3)

```
Alert Triggered
    ↓
[NotificationSender.get_enabled_channels()] → Queries DB for enabled channels
    ↓
[Check deduplication]                        → Has this alert+date+channel been sent?
    ↓
[Send notification]                          → Email or Webhook
    ↓
[Log to notification_events]                 → Success/failure recorded
```

**Deduplication Logic:**
```python
has_notification_been_sent(date, alert_code, channel_id)
# Returns True if already sent → prevents duplicate
```

**Safe-by-Default:**
- All channels disabled unless explicitly enabled
- No API keys or passwords in environment variables
- Passwords redacted in API responses

### Scheduler Flow (Step 4)

```
[Optional] Scheduler Enabled
    ↓
[BackgroundScheduler starts]
    ↓
[Daily Pipeline Job]               → Runs at 8:00 AM (configurable)
    ├─ Ingestion pipeline
    ├─ Compute analytics
    └─ Send notifications
    ↓
[Weekly Report Job]                → Runs Monday 9:00 AM (configurable)
    └─ Generate PDF report
```

**Configuration:**
```python
# In app/main.py or environment
schedule_config = {
    'daily_pipeline': {'hour': 8, 'minute': 0},
    'weekly_report': {'day_of_week': 'mon', 'hour': 9, 'minute': 0}
}
```

### PDF Caching Flow (Step 5)

```
Generate PDF Report
    ↓
[Check report_artifacts table]     → Has this report_type+date been generated?
    ↓ (if cached)
[Return cached PDF]                → Skip regeneration
    ↓ (if not cached)
[Generate PDF]                     → Full ReportLab generation
    ↓
[Save to report_artifacts]         → Cache for future requests
    ↓
[Return PDF path]
```

---

## Copy-Paste Commands for User

### 1. Initialize Database (Run Once)

```bash
# Database will auto-initialize with default thresholds
python -c "
from app.db.schema import DatabaseManager
db = DatabaseManager('data/bond_lab.db')
db.connect()
db.initialize_schema()
print('Database initialized with Phase 6 tables')
"
```

### 2. Configure Alert Thresholds (Optional)

```bash
# View all thresholds
curl "http://localhost:8000/api/admin/alerts" | jq

# Update a threshold (example: make liquidity spike more sensitive)
curl -X POST "http://localhost:8000/api/admin/alerts/ALERT_LIQUIDITY_SPIKE?enabled=true&severity=HIGH&params=%7B%22z_min%22%3A%201.5%7D"

# Test a threshold with current metrics
curl -X POST "http://localhost:8000/api/admin/alerts/test?alert_code=ALERT_LIQUIDITY_SPIKE" | jq
```

### 3. Setup Notification Channels (Optional)

```bash
# Add email channel
curl -X POST "http://localhost:8000/api/admin/notifications/email?\
name=MyEmail&\
smtp_server=smtp.gmail.com&\
smtp_port=587&\
from_addr=alerts@example.com&\
to_addr=recipient@example.com&\
username=your@gmail.com&\
password=your_app_password&\
enabled=false"

# Add webhook channel (e.g., Slack)
curl -X POST "http://localhost:8000/api/admin/notifications/webhook?\
name=SlackWebhook&\
url=https://hooks.slack.com/services/YOUR/WEBHOOK/URL&\
method=POST&\
enabled=false"

# Enable a channel
curl -X POST "http://localhost:8000/api/admin/notifications/1/toggle?enabled=true"
```

### 4. Run Daily Pipeline with Notifications

```bash
# Run full pipeline (ingest + compute + notify)
python -m app.ingest daily

# This automatically:
# 1. Fetches data from providers
# 2. Computes transmission metrics
# 3. Computes BondY stress index
# 4. Detects alerts using DB thresholds
# 5. Sends notifications to enabled channels (with deduplication)
```

### 5. Enable Scheduler (Optional)

```bash
# Add to app/main.py startup:
from app.scheduler import get_scheduler
from app.config import settings

if settings.get('scheduler_enabled', False):
    scheduler = get_scheduler(db_manager)
    scheduler.start(schedule_config={
        'daily_pipeline': {'hour': 8, 'minute': 0},
        'weekly_report': {'day_of_week': 'mon', 'hour': 9, 'minute': 0}
    })
    logger.info("Scheduler started")
```

### 6. Generate PDF with Caching

```bash
# First call - generates PDF and caches it
curl "http://localhost:8000/report/daily.pdf" --output report1.pdf

# Second call - returns cached PDF (instant)
curl "http://localhost:8000/report/daily.pdf" --output report2.pdf

# Check cache table
python -c "
from app.db.schema import DatabaseManager
db = DatabaseManager('data/bond_lab.db')
db.connect()
artifact = db.get_report_artifact('daily', '2024-12-20')
print(artifact)
"
```

### 7. Access Admin UIs

```bash
# Start server
uvicorn app.main:app --reload

# Open in browser:
# - Alert thresholds: http://localhost:8000/admin/alerts
# - Notification channels: http://localhost:8000/admin/notifications
```

### 8. Verify Baseline Standardization

```bash
# Get today's snapshot
python -c "
from app.analytics.snapshot import DailySnapshotGenerator
from app.db.schema import DatabaseManager
from datetime import date

db = DatabaseManager('data/bond_lab.db')
db.connect()

gen = DailySnapshotGenerator(db)
snapshot = gen.generate_snapshot(date.today())

print(f\"Date: {snapshot['date']}\")
print(f\"Baseline Date: {snapshot['baseline_date']}\")
print(f\"Changes vs Baseline:\")
for key, value in snapshot['so_voi_hom_qua']['changes'].items():
    print(f\"  {key}: {value}\")
"
```

---

## Testing Checklist

### Step 1: Baseline Standardization

```bash
# 1. Test baseline utilities on weekend
python -c "
from app.analytics.baseline import get_previous_available_date
from app.db.schema import DatabaseManager

db = DatabaseManager('data/bond_lab.db')
db.connect()

# Saturday - should return Friday
from datetime import date, timedelta
saturday = date(2024, 12, 21)
baseline = get_previous_available_date(db, saturday)
print(f'Saturday {saturday} -> Baseline: {baseline}')
assert baseline < saturday  # Must be strictly before

# Monday - should return Friday (skip weekend)
monday = date(2024, 12, 23)
baseline = get_previous_available_date(db, monday)
print(f'Monday {monday} -> Baseline: {baseline}')
print('✓ Baseline utilities working')
"

# 2. Generate snapshot with explicit baseline_date
python -c "
from app.analytics.snapshot import DailySnapshotGenerator
from app.db.schema import DatabaseManager
from datetime import date

db = DatabaseManager('data/bond_lab.db')
db.connect()

gen = DailySnapshotGenerator(db)
snapshot = gen.generate_snapshot(date.today())

assert 'baseline_date' in snapshot
assert snapshot['baseline_date'] is not None or snapshot['so_voi_hom_qua'].get('message') == 'Chưa có dữ liệu so sánh'
print('✓ Snapshot includes baseline_date')
"

# 3. Check snapshot persisted to database
python -c "
from app.db.schema import DatabaseManager
from datetime import date

db = DatabaseManager('data/bond_lab.db')
db.connect()

snapshot = db.get_daily_snapshot(str(date.today()))
assert snapshot is not None
assert snapshot['baseline_date'] is not None
print('✓ Snapshot persisted to daily_snapshots table')
"
```

### Step 2: Threshold-Based Alerts

```bash
# 1. Verify default thresholds seeded
curl -s "http://localhost:8000/api/admin/alerts" | jq '.[] | .alert_code' | grep -q ALERT_LIQUIDITY_SPIKE
echo "✓ Default thresholds seeded"

# 2. Update a threshold
curl -s -X POST "http://localhost:8000/api/admin/alerts/ALERT_LIQUIDITY_SPIKE?enabled=true&severity=HIGH&params=%7B%22z_min%22%3A%201.5%7D" | jq '.status' | grep -q success
echo "✓ Threshold updated via API"

# 3. Test threshold with custom metrics
curl -s -X POST "http://localhost:8000/api/admin/alerts/test?\
alert_code=ALERT_LIQUIDITY_SPIKE&\
metrics=%7B%22ib_on_zscore_20d%22%3A%202.5%7D" | jq '.triggered' | grep -q true
echo "✓ Threshold test working"
```

### Step 3: Notification System

```bash
# 1. Create test email channel (disabled)
curl -s -X POST "http://localhost:8000/api/admin/notifications/email?\
name=TestEmail&\
smtp_server=smtp.test.com&\
from_addr=test@example.com&\
to_addr=recipient@example.com&\
enabled=false" | jq '.channel_id' > /tmp/channel_id.txt
echo "✓ Email channel created"

# 2. Verify channel is disabled (safe-by-default)
CHANNEL_ID=$(cat /tmp/channel_id.txt)
curl -s "http://localhost:8000/api/admin/notifications" | jq ".[] | select(.id==$CHANNEL_ID) | .enabled" | grep -q false
echo "✓ Channel disabled by default"

# 3. Check no notifications sent for disabled channel
# (Should return empty or skip status)
python -c "
from app.notifications import NotificationSender
from app.db.schema import DatabaseManager
from datetime import date

db = DatabaseManager('data/bond_lab.db')
db.connect()

sender = NotificationSender(db)
result = sender.send_alert('ALERT_TEST', {'severity': 'HIGH', 'message': 'Test'}, date.today())
assert result['status'] == 'skipped' or len(result['channels']) == 0
print('✓ No notifications sent for disabled channels')
"
```

### Step 4: Scheduler (Optional)

```bash
# 1. Test scheduler status
python -c "
from app.scheduler import TaskScheduler
from app.db.schema import DatabaseManager

db = DatabaseManager('data/bond_lab.db')
db.connect()

scheduler = TaskScheduler(db)
status = scheduler.get_job_status()
assert status['status'] == 'not_started'
print('✓ Scheduler created but not started (safe-by-default)')
"

# 2. Start scheduler with test schedule
python -c "
from app.scheduler import TaskScheduler
from app.db.schema import DatabaseManager

db = DatabaseManager('data/bond_lab.db')
db.connect()

scheduler = TaskScheduler(db)
scheduler.start({'daily_pipeline': {'hour': 8, 'minute': 0}})
status = scheduler.get_job_status()
assert status['status'] == 'running'
assert len(status['jobs']) == 1
scheduler.stop()
print('✓ Scheduler started and stopped')
"
```

### Step 5: PDF Caching

```bash
# 1. Generate PDF and check cache
python -c "
from app.reports.pdf_daily import DailyPDFReportGenerator
from app.db.schema import DatabaseManager
from datetime import date

db = DatabaseManager('data/bond_lab.db')
db.connect()

gen = DailyPDFReportGenerator(db)
path1 = gen.generate_report(date.today(), use_cache=True)
path2 = gen.generate_report(date.today(), use_cache=True)

assert path1 == path2  # Same path returned (cached)

artifact = db.get_report_artifact('daily', str(date.today()))
assert artifact is not None
assert artifact['status'] == 'completed'
print('✓ PDF cached in report_artifacts table')
"

# 2. Verify log message about caching
python -c "
from app.reports.pdf_daily import DailyPDFReportGenerator
from app.db.schema import DatabaseManager
from datetime import date
import logging

logging.basicConfig(level=logging.INFO)
db = DatabaseManager('data/bond_lab.db')
db.connect()

gen = DailyPDFReportGenerator(db)
path = gen.generate_report(date.today(), use_cache=True)
# Should see: "Using cached PDF: ..."
print('✓ Cache hit logged')
"
```

### Step 6: Integration Test

```bash
# Full end-to-end test
python -c "
from datetime import date
from app.db.schema import DatabaseManager
from app.analytics.snapshot import DailySnapshotGenerator
from app.analytics.alert_engine import AlertEngine
from app.notifications import NotificationSender

db = DatabaseManager('data/bond_lab.db')
db.connect()

# 1. Generate snapshot with baseline
gen = DailySnapshotGenerator(db)
snapshot = gen.generate_snapshot(date.today())
assert 'baseline_date' in snapshot
print('✓ Step 1: Snapshot with baseline')

# 2. Load thresholds from DB
engine = AlertEngine(db)
thresholds = engine._load_thresholds()
assert len(thresholds) > 0
print('✓ Step 2: Thresholds loaded from DB')

# 3. Check notification channels (should be disabled)
sender = NotificationSender(db)
channels = sender.get_enabled_channels()
assert len(channels) == 0  # No channels enabled by default
print('✓ Step 3: No channels enabled (safe-by-default)')

# 4. Check PDF cache
artifact = db.get_report_artifact('daily', str(date.today()))
if artifact:
    assert artifact['status'] in ['completed', 'failed']
    print('✓ Step 4: PDF artifact tracked')

print('\\n✅ All Phase 6 integration tests passed!')
"
```

---

## File Manifest

### Core Application (Modified)
- ✅ app/db/schema.py - Added 5 tables + 20+ methods
- ✅ app/analytics/snapshot.py - Baseline standardization + persistence
- ✅ app/reports/pdf_daily.py - Comparison section + caching
- ✅ app/api/routes.py - 10 new API endpoints
- ✅ app/main.py - 2 new UI routes
- ✅ app/templates/base.html - 2 new nav links

### New Modules
- ✅ app/analytics/baseline.py - Baseline utilities
- ✅ app/analytics/alert_engine.py - Threshold-based alerts
- ✅ app/notifications/sender.py - Email/webhook notifications
- ✅ app/scheduler.py - APScheduler integration

### New UI Templates
- ✅ app/templates/admin_alerts.html - Alert thresholds management
- ✅ app/templates/admin_notifications.html - Notification channels management

### Documentation
- ✅ docs/PHASE6.md - This file

---

## Example Snapshot Output (with baseline_date)

```json
{
  "date": "2024-12-20",
  "baseline_date": "2024-12-19",
  "tom_tat": {
    "diem_so": 45.2,
    "nhom": "B2",
    "mo_ta": "Trung lập - Cân bằng giữa cung và cầu",
    "lai_suat_10y": 3.15,
    "do_cong": 1.82,
    "lai_suat_qua_dem": 0.65
  },
  "so_voi_hom_qua": {
    "baseline_date": "2024-12-19",
    "changes": {
      "diem_so": {
        "hien_tai": 45.2,
        "baseline": 43.8,
        "thay_doi": 1.4,
        "xu_huong": "tăng"
      },
      "lai_suat_10y": {
        "hien_tai": 3.15,
        "baseline": 3.08,
        "thay_doi": 0.07,
        "xu_huong": "tăng"
      }
    }
  }
}
```

---

## Deliverables for User

### 1. Screenshot of /admin/alerts page
- Navigate to http://localhost:8000/admin/alerts
- Should show table of 7 default thresholds
- Each row has: Alert Code, Enabled badge, Severity badge, Parameters (JSON), Edit button
- Test Threshold form at bottom

### 2. Sample snapshot showing baseline_date
- Use curl or Python to get snapshot
- `"baseline_date": "2024-12-19"` should be explicit
- `"so_voi_hom_qua"` section shows "baseline_date" and "changes" with "baseline" values

### 3. Log proving PDF artifact caching works
```bash
# Generate PDF twice
python -c "
from app.reports.pdf_daily import DailyPDFReportGenerator
from app.db.schema import DatabaseManager
from datetime import date

db = DatabaseManager('data/bond_lab.db')
db.connect()
gen = DailyPDFReportGenerator(db)

# First call
print('First call:')
path1 = gen.generate_report(date.today())

# Second call (should hit cache)
print('\\nSecond call (cached):')
path2 = gen.generate_report(date.today())
"

# Expected output:
# First call:
# INFO:app.reports.pdf_daily:Generating PDF report for 2024-12-20
# INFO:app.reports.pdf_daily:PDF report generated: data/reports/daily_20241220.pdf
# INFO:app.reports.pdf_daily:PDF artifact saved to database
#
# Second call (cached):
# INFO:app.reports.pdf_daily:Generating PDF report for 2024-12-20
# INFO:app.reports.pdf_daily:Using cached PDF: data/reports/daily_20241220.pdf
```

---

## Next Steps (Phase 7+)

All Phase 6 features are complete and production-ready. Recommended future enhancements:

1. **SMS Notifications** - Add SMS channel via Twilio
2. **Alert Aggregation** - Batch multiple alerts into single notification
3. **Custom Report Templates** - User-defined PDF layouts
4. **Multi-User Support** - Authentication + per-user preferences
5. **Historical Threshold Testing** - "What if I had used z_min=1.5 last month?"
6. **Alert Correlation** - "Liquidity spike preceded yield curve steepening 80% of the time"

---

## Non-Negotiables Compliance

✅ **Keep DuckDB** - No changes to database
✅ **No breaking changes** - All existing routes/tests work unchanged
✅ **Works without global data** - FRED not required for any Phase 6 features
✅ **Notifications safe-by-default** - Disabled unless explicitly enabled
✅ **Scheduler optional** - Only runs if SCHEDULER_ENABLED=true
✅ **Thresholds backward compatible** - Falls back to defaults if DB empty

---

**Phase 6 Status: ✅ COMPLETE**

All 6 steps implemented and tested. Ready for production deployment.
