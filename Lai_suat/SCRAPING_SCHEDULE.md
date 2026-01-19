# Scheduled Scraping Guide

## Overview

This guide explains how to set up automated daily scraping to accumulate historical interest rate data. The scraper collects data from multiple sources and stores it in the database for the "Lịch sử" (History) tab to display trends over time.

**📚 Data Semantics**: See [DATA_SEMANTICS.md](DATA_SEMANTICS.md) for details on:
- Raw layer: Multiple sources can store observations per day
- Canonical layer: Endpoints return 1 point/day using source priority
- Unique keys include `source_id` to enable raw-all-sources storage

## Why Schedule Scraping?

Currently, the database only has **1 day of observations** (scraped once on `2026-01-06`). To enable meaningful historical analysis:

- **Minimum**: 2-3 days of data → basic trend line
- **Recommended**: 7-30 days of data → clear trend patterns
- **Ideal**: 90+ days of data → seasonal/long-term trends

## Prerequisites

**⚠️ REQUIRED: Run Data Integrity Migration**

Before scheduling scraping, you MUST run the migration to enable per-day deduplication:

```bash
cd /path/to/backend
python3 -m app.migrations.run_migration add_observed_day.sql
```

**What this does:**
- Adds `observed_day` column for daily tracking
- Creates unique index to prevent duplicate observations per day
- Enables `distinct_days_overall` field in `/meta/latest` endpoint

**Verify migration success:**
```bash
# Should show 2+ distinct days if you have data
curl -s http://localhost:8001/meta/latest | jq '.distinct_days_overall'
```

---

### Other Prerequisites

1. Backend server running: `http://localhost:8001`
2. Database configured: SQLite/PostgreSQL
3. Python 3.9+ installed
4. (Optional) Virtual environment activated

---

## Option A: Cron (macOS/Linux)

### A.1. Create Cron Job

Edit crontab:
```bash
crontab -e
```

Add the following line to run scraping daily at 02:00 AM:
```bash
# Scrape interest rates daily at 02:00 AM
# flock prevents overlapping runs (non-blocking, fails if lock held)

# For system Python:
0 2 * * * cd /path/to/backend && flock -n /tmp/interest-rates-scraper.lock -c "/usr/bin/python3 -m app.cli scrape --all" >> /var/log/interest-rates-scraper.log 2>&1

# For virtual environment (update path):
# 0 2 * * * cd /path/to/backend && flock -n /tmp/interest-rates-scraper.lock -c "/path/to/backend/venv/bin/python -m app.cli scrape --all" >> /var/log/interest-rates-scraper.log 2>&1
```

**Breakdown**:
- `0 2 * * *` → Run at 02:00 AM every day
- `cd /path/to/backend` → Change to backend directory (update path)
- `flock -n /tmp/interest-rates-scraper.lock` → Prevent concurrent runs
- `/usr/bin/python3` → Python executable path (check with `which python3`)
- `-m app.cli scrape --all` → Run scraper for all sources
- `>> /var/log/interest-rates-scraper.log 2>&1` → Append logs to file

### A.2. Verify Cron Job

List current cron jobs:
```bash
crontab -l
```

Check if scraper ran successfully:
```bash
# View log file
tail -f /var/log/interest-rates-scraper.log

# Or check recent entries
tail -50 /var/log/interest-rates-scraper.log
```

### A.3. Manual Test Run

Test the scraper manually before scheduling:
```bash
cd /path/to/backend
/usr/bin/python3 -m app.cli scrape --all
```

Expected output:
```
Starting scraper...
[24hmoney] Scraping deposit rates...
[24hmoney] Scraping loan rates...
[timo] Scraping deposit rates...
[timo] Scraping loan rates...
Scraper completed. Total observations: 386
```

### A.4. Verify Database Has Multiple Days

After 2-3 days of scraping, verify data accumulation:

```bash
# Check distinct days overall
curl -s http://localhost:8001/meta/latest | jq '.distinct_days_overall'

# Check distinct days per series
sqlite3 data/rates.db "
SELECT s.code, COUNT(DISTINCT date(o.observed_at)) AS days
FROM series s
JOIN observations o ON o.series_id = s.id
GROUP BY s.code
ORDER BY days ASC;
"
```

Expected output (after 3 days):
```
3           # ← 3 distinct days overall

deposit_online|2
deposit_tai_quay|3
loan_the_chap|1
loan_tin_chap|2
```

---

## Option B: systemd (Linux)

### B.1. Install Service and Timer Files

Copy the provided templates to systemd directory:
```bash
sudo cp backend/deploy/systemd/interest-rates-scraper.service /etc/systemd/system/
sudo cp backend/deploy/systemd/interest-rates-scraper.timer /etc/systemd/system/
```

**Update placeholders** in `/etc/systemd/system/interest-rates-scraper.service`:
- `User=www-data` → Change to your user (e.g., `User=ubuntu`)
- `WorkingDirectory=/path/to/backend` → Absolute path to backend directory
- `ExecStart=...` → Update Python path if using venv

### B.2. Service File Features

The service file includes several hardening features:

**1. Lock-based Concurrency Control**:
```bash
ExecStart=/usr/bin/bash -c 'flock -n /var/run/interest-rates-scraper.lock -c "/usr/bin/python3 -m app.cli scrape --all"'
```
- `flock -n` → Non-blocking lock, fails immediately if scraper already running
- Prevents overlap if previous run takes too long

**2. Timeouts**:
```ini
TimeoutStartSec=600  # Kill scraper if it runs >10 minutes
TimeoutStopSec=30     # Allow 30 seconds for graceful shutdown
```

**3. Proper Logging**:
```ini
StandardOutput=append:/var/log/interest-rates-scraper.log
StandardError=append:/var/log/interest-rates-scraper.log
```

### B.3. Timer Configuration

Timer file (`interest-rates-scraper.timer`):
```ini
[Timer]
OnCalendar=*-*-* 02:00:00  # Run daily at 02:00 AM
Persistent=true              # Run immediately on boot if scheduled time was missed
AccuracySec=1min             # Fire within 1 minute of scheduled time
```

### B.4. Enable and Start Timer

```bash
# Reload systemd configuration
sudo systemctl daemon-reload

# Enable timer to start on boot
sudo systemctl enable interest-rates-scraper.timer

# Start timer immediately
sudo systemctl start interest-rates-scraper.timer

# Check timer status
sudo systemctl list-timers | grep interest-rates

# Check last/next run time
sudo systemctl status interest-rates-scraper.timer
```

### B.5. Manual Trigger (Testing)

Run scraper immediately without waiting for schedule:
```bash
# Trigger service manually
sudo systemctl start interest-rates-scraper.service

# Check service logs
sudo journalctl -u interest-rates-scraper.service -f

# Or view log file
sudo tail -f /var/log/interest-rates-scraper.log
```

### B.6. Monitor and Verify

Check scraper logs:
```bash
# Follow logs in real-time
sudo journalctl -u interest-rates-scraper.service -f

# View last 50 entries
sudo journalctl -u interest-rates-scraper.service -n 50

# Check if service ran successfully
sudo systemctl status interest-rates-scraper.service
```

Expected status output:
```
● interest-rates-scraper.service - Interest Rates Scraper
   Loaded: loaded (/etc/systemd/system/interest-rates-scraper.service; enabled)
   Active: inactive (dead) since Mon 2026-01-06 02:00:15 UTC; 5h ago
 Main PID: 12345 (code=exited, status=0/SUCCESS)
```

---

## Option C: Manual Trigger (Ad-hoc)

### C.1. Run Scraper Immediately

```bash
cd /path/to/backend
/usr/bin/python3 -m app.cli scrape --all
```

### C.2. Verify Results

Check API endpoint to confirm new data:
```bash
# Check latest scrape timestamp
curl -s http://localhost:8001/meta/latest | jq '.latest_scraped_at'

# Check distinct observation days
curl -s http://localhost:8001/series | jq 'length'

# Test history endpoint with known data
curl -s "http://localhost:8001/history?bank_name=OCB&series_code=deposit_online&term_months=12" | jq '.points | length'
```

---

## Concurrency Control

### Why Locking Matters

Without locking, scheduled scrapes can overlap:
- **Scenario**: Previous scrape runs at 02:00, takes 15 minutes
- **Risk**: If next day's cron fires at 02:05, two scrapers run simultaneously
- **Consequence**: Duplicate data, DB lock contention, increased load

### Flock-based Solutions

**Cron with flock**:
```bash
flock -n /tmp/interest-rates-scraper.lock -c "python3 -m app.cli scrape --all"
```
- `-n` → Non-blocking, exits immediately if lock held
- If scraper is running, cron job will skip (check logs for "flock: ...")

**systemd with flock**:
```bash
ExecStart=/usr/bin/bash -c 'flock -n /var/run/interest-rates-scraper.lock -c "/usr/bin/python3 -m app.cli scrape --all"'
```
- Same behavior, integrated into systemd service

---

## Verification Checklist

After setting up scheduled scraping, verify:

- [ ] Cron job OR systemd timer is enabled
- [ ] Scraper runs successfully at scheduled time
- [ ] Log file shows no errors
- [ ] Database has increasing distinct days
- [ ] API `/meta/latest` shows updated timestamp
- [ ] Frontend "Lịch sử" tab shows data (after 2+ days)
- [ ] No overlapping runs (check logs for timestamps)

### Quick Verification Commands

```bash
# 1. Check if cron/systemd is scheduled
crontab -l | grep scrape
sudo systemctl list-timers | grep interest-rates

# 2. Check last scrape time
curl -s http://localhost:8001/meta/latest | jq -r '.latest_scraped_at'

# 3. Check distinct days in DB
sqlite3 data/rates.db "SELECT COUNT(DISTINCT date(observed_at)) FROM observations;"

# 4. Check a specific history endpoint
curl -s "http://localhost:8001/history?bank_name=OCB&series_code=deposit_online&term_months=12" | jq '.points | length'

# 5. Check scraper log for errors
tail -20 /var/log/interest-rates-scraper.log
# OR for systemd:
sudo journalctl -u interest-rates-scraper.service -n 20 --no-pager
```

---

## Troubleshooting

### Issue: Scraper runs but no new data

**Symptoms**: Log shows "Scraper completed" but DB has same date

**Diagnosis**:
```bash
# Check if data actually changed
sqlite3 data/rates.db "SELECT MAX(observed_at), MIN(observed_at), COUNT(*) FROM observations;"

# Check if sources returned rates
tail -50 /var/log/interest-rates-scraper.log | grep -E "(Scraping|observations)"
```

**Solution**: Sources may not have updated rates. This is normal if rates haven't changed.

### Issue: Cron job doesn't run

**Symptoms**: `/var/log/interest-rates-scraper.log` not updated

**Diagnosis**:
```bash
# Check cron service
sudo systemctl status cron

# Check if crontab is loaded
crontab -l

# Check cron logs (Ubuntu/Debian)
sudo grep CRON /var/log/syslog | tail -20
```

**Solution**:
```bash
# Restart cron service
sudo systemctl restart cron

# Verify crontab syntax
crontab -l | grep -v "^#" | crontab -
```

### Issue: systemd timer doesn't trigger

**Symptoms**: `systemctl status` shows "Last run: n/a"

**Diagnosis**:
```bash
# Check if timer is active
sudo systemctl status interest-rates-scraper.timer

# Check system clock
timedatectl

# Check timer logs
sudo journalctl -u interest-rates-scraper.timer -n 50
```

**Solution**:
```bash
# Restart timer
sudo systemctl restart interest-rates-scraper.timer

# Re-enable if needed
sudo systemctl enable interest-rates-scraper.timer

# Check Persistent=true (catch-up if system was off)
sudo cat /etc/systemd/system/interest-rates-scraper.timer | grep Persistent
```

### Issue: "flock: resource temporarily unavailable"

**Symptoms**: Log shows flock error

**Cause**: Previous scraper still running (lock held)

**Diagnosis**:
```bash
# Check if Python processes are running
ps aux | grep "[p]ython.*app.cli"
```

**Solution**:
```bash
# Wait for current run to finish
# OR kill stuck process
pkill -f "app.cli scrape"

# Then manual run
cd /path/to/backend && /usr/bin/python3 -m app.cli scrape --all
```

### Issue: "Module not found" error

**Symptoms**: Log shows `ModuleNotFoundError: No module named 'app'`

**Solution**:
```bash
# Use absolute path to Python in venv (if using venv)
/home/user/.local/bin/poetry run python -m app.cli scrape --all

# OR activate venv first
source /path/to/backend/venv/bin/activate
python -m app.cli scrape --all
```

---

## Advanced: Multiple Scrapes Per Day

For more granular data, scrape multiple times per day:

### Cron (4x daily: 02:00, 08:00, 14:00, 20:00)
```bash
0 2,8,14,20 * * * cd /path/to/backend && flock -n /tmp/interest-rates-scraper.lock -c "/usr/bin/python3 -m app.cli scrape --all" >> /var/log/interest-rates-scraper.log 2>&1
```

### systemd (modify OnCalendar)
```ini
[Timer]
OnCalendar=*-*-* 02,08,14,20:00:00
Persistent=true
```

**Note**: More frequent scraping = better historical data, but:
- Higher API load on sources
- Larger database size
- May not be necessary (rates typically don't change intra-day)

---

## Summary

**For production use**, recommended setup:

1. Use **systemd timer** (Linux) or **cron** (macOS/Linux)
2. Scrape **once daily at 02:00 AM** (off-peak hours)
3. Use **flock** to prevent overlapping runs
4. Monitor logs for errors weekly
5. Verify data accumulation monthly
6. After 30+ days, "Lịch sử" tab will show meaningful trends

**For testing/development**, run manual scrape:
```bash
cd /path/to/backend
/usr/bin/python3 -m app.cli scrape --all
```

---

**Last updated**: 2026-01-06 (Phase 2: Added flock + renamed to interest-rates-scraper)
**Maintainer**: Backend Team
