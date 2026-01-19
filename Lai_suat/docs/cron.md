# Cron Job Setup for Automatic Scraping

This guide explains how to set up automated scraping jobs using cron on Linux/macOS.

---

## Exit Codes

The scraper uses the following exit codes:

- **0**: Success (all sources scraped successfully)
- **2**: Anomaly detected (e.g., record count dropped by >30%)
- **3**: Fatal error (e.g., network failure, parse error)

**Important**: Exit code `2` (anomaly) is **NOT** a failure - it's a warning that needs attention but the job completed.

---

## Cron Entry Examples

### Every 6 Hours (Recommended)

```cron
# Scrape bank rates every 6 hours (at 00:00, 06:00, 12:00, 18:00)
0 */6 * * * cd /path/to/Lai_suat && /usr/bin/env bash scripts/run_scrape_job.sh >> logs/scrape_cron.log 2>&1
```

### Every 2 Hours

```cron
# Scrape bank rates every 2 hours
0 */2 * * * cd /path/to/Lai_suat && /usr/bin/env bash scripts/run_scrape_job.sh >> logs/scrape_cron.log 2>&1
```

### Daily at 1 AM

```cron
# Scrape bank rates daily at 1 AM
0 1 * * * cd /path/to/Lai_suat && /usr/bin/env bash scripts/run_scrape_job.sh >> logs/scrape_$(date +\%Y\%m\%d).log 2>&1
```

---

## Setup Instructions

### 1. Create Log Directory

```bash
mkdir -p logs
```

### 2. Make Script Executable

```bash
chmod +x scripts/run_scrape_job.sh
```

### 3. Edit Crontab

```bash
crontab -e
```

### 4. Add Cron Entry

Choose one of the examples above and adjust:
- `/path/to/Lai_suat` → Your actual repository path
- Schedule → Your preferred frequency

### 5. Verify Cron Job

List your cron jobs:
```bash
crontab -l
```

---

## Log Management

### Simple Rotation (Manual)

```bash
# Archive old logs
mv logs/scrape_cron.log logs/scrape_cron_$(date +%Y%m%d).log

# Or compress old logs
gzip logs/scrape_cron_$(date +%Y%m%d).log
```

### Logrotate (Linux)

Create `/etc/logrotate.d/lai_suat`:

```
/path/to/Lai_suat/logs/scrape_cron.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
}
```

---

## Monitoring

### Check Latest Scrape Status

```bash
# Via API (recommended)
curl http://localhost:8001/status

# Or check logs
tail -50 logs/scrape_cron.log
```

### Monitor Exit Codes in Logs

```bash
# Check for anomalies (exit code 2)
grep "exit code 2" logs/scrape_cron.log

# Check for errors (exit code 3)
grep "exit code 3" logs/scrape_cron.log
```

---

## Troubleshooting

### Job Not Running?

1. Check cron is running:
   ```bash
   # Linux
   sudo systemctl status cron

   # macOS
   sudo launchctl list | grep cron
   ```

2. Check cron logs:
   ```bash
   # Linux
   sudo grep CRON /var/log/syslog

   # macOS
   log show --predicate 'eventMessage contains "cron"' --last 1h
   ```

3. Verify script path is absolute:
   ```bash
   # Use absolute paths in cron
   /Users/username/Lai_suat/scripts/run_scrape_job.sh
   ```

### Environment Variables Not Loaded?

Cron runs with a minimal environment. If your job fails due to missing environment:

1. Use the wrapper script (`run_scrape_job.sh`) which activates the venv
2. Or specify full paths in crontab:
   ```cron
   SHELL=/bin/bash
   PATH=/usr/local/bin:/usr/bin:/bin
   ```

---

## Testing

Before adding to cron, test the script manually:

```bash
# Run once
./scripts/run_scrape_job.sh

# Check exit code
echo $?
# Should be 0, 2, or 3

# Verify data was scraped
python3 -c "from app.db import Database; db = Database('data/rates.db'); print(f'Sources: {len(db.get_all_sources())}')"
```

---

## Advanced: Anomaly Alerts

You can extend the script to send alerts on anomalies:

```bash
# In run_scrape_job.sh, after scrape
if [ $EXIT_CODE -eq 2 ]; then
    echo "Anomaly detected in bank rate scraping" | mail -s "Lai Suat Scraper Warning" admin@example.com
fi
```

Or use monitoring tools like:
- **Uptime Kuma**: Monitor `/status` endpoint
- **Prometheus**: Export metrics
- **CloudWatch**: If running on AWS

---

## Production Tips

1. **Schedule**: Run every 6 hours (banks typically update rates once/twice daily)
2. **Retry**: If exit code 3 (fatal), consider retrying after 30 minutes
3. **Monitoring**: Set up alerts for consecutive failures
4. **Backups**: Backup database regularly:
   ```bash
   cp data/rates.db data/rates.db.backup.$(date +%Y%m%d)
   ```

---

**Last Updated**: 2026-01-05
