# Scrape Job Runner

Production-friendly script to run scraping jobs with logging and monitoring.

## Usage

```bash
# Scrape all sources
python scripts/run_scrape_job.py --all

# Scrape specific source
python scripts/run_scrape_job.py --source timo_deposit

# Scrape all deposit sources
python scripts/run_scrape_job.py --kind deposit

# With custom anomaly threshold
python scripts/run_scrape_job.py --all --anomaly-threshold 0.25

# Log anomalies but don't fail
python scripts/run_scrape_job.py --all --no-anomaly-exit
```

## Features

- ✅ Logs to `logs/scrape_YYYYMMDD.log` (daily rotating)
- ✅ Console and file logging
- ✅ Exit codes: 0 (success), 2 (anomaly), 3 (fatal)
- ✅ Supports --all, --source, --kind flags
- ✅ Anomaly detection with configurable threshold
- ✅ Can be scheduled via cron or APScheduler

## Exit Codes

- **0**: Success (no anomalies or --no-anomaly-exit used)
- **2**: Anomaly detected (record count drop > threshold)
- **3**: Fatal scrape failure

## Scheduling

### Cron (Linux/macOS)

```bash
# Edit crontab
crontab -e

# Add job to run every 6 hours
0 */6 * * * cd /path/to/Lai_suat && python scripts/run_scrape_job.py --all >> logs/cron.log 2>&1
```

### Launchd (macOS)

Create `~/Library/LaunchAgents/com.laisuat.scrape.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.laisuat.scrape</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/Lai_suat/scripts/run_scrape_job.py</string>
        <string>--all</string>
    </array>
    <key>StartInterval</key>
    <integer>21600</integer> <!-- 6 hours = 21600 seconds -->
    <key>WorkingDirectory</key>
    <string>/path/to/Lai_suat</string>
    <key>StandardOutPath</key>
    <string>/path/to/Lai_suat/logs/scrape_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/Lai_suat/logs/scrape_stderr.log</string>
</dict>
</plist>
```

Load with:
```bash
launchctl load ~/Library/LaunchAgents/com.laisuat.scrape.plist
launchctl start com.laisuat.scrape
```

## Monitoring

Check logs:
```bash
# Today's log
tail -f logs/scrape_$(date +%Y%m%d).log

# All logs
ls -la logs/
```

Check database for latest data:
```bash
sqlite3 data/rates.db "SELECT scraped_at, COUNT(*) FROM sources GROUP BY scraped_at ORDER BY scraped_at DESC LIMIT 5;"
```
