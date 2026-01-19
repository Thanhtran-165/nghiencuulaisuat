# Provider Probe Command - Quick Reference

## What is the Provider Probe?

The provider probe is a diagnostic tool that tests each data provider's capabilities. It answers:
- Can this provider fetch today's data?
- Can this provider fetch yesterday's data?
- Can this provider fetch historical data (2013-01-01)?
- Does this provider support backfill?
- What errors occur when testing?

## How to Run

### Option 1: Via Docker (Recommended)

```bash
# Make sure the app is running
docker compose up -d

# Probe all providers
docker compose run --rm app python -m app.ingest probe

# Probe specific providers
docker compose run --rm app python -m app.ingest probe --providers hnx_yield_curve sbv_interbank
```

### Option 2: From Admin UI

1. Open `http://localhost:8000/admin/ingest`
2. Find "Provider Status" panel
3. Click "Run Provider Probe" button
4. Wait for completion (1-2 minutes)
5. Status refreshes automatically

## Understanding the Output

### Console Output

```
============================================================
PROBE SUMMARY
============================================================

hnx_yield_curve:
  fetch_latest:       ✓
  fetch_yesterday:    ✗
  fetch_historical:   ✗
  backfill_supported: ✓
  failure_modes: fetch_yesterday: ProviderError
  earliest_success: 2026-01-13

hnx_ftp_pdf:
  fetch_latest:       ✓
  fetch_yesterday:    ✓
  fetch_historical:   ✓
  backfill_supported: ✓
  earliest_success: 2013-01-01
```

**Legend**:
- ✓ = Capability works
- ✗ = Capability failed
- failure_modes = Error types that occurred
- earliest_success = Oldest date successfully fetched

### JSON Report

Saved to: `reports/provider_probe.json`

**Structure**:
```json
{
  "probe_timestamp": "When probe ran",
  "providers": {
    "provider_name": {
      "capabilities": {
        "fetch_latest": true/false,
        "fetch_yesterday": true/false,
        "fetch_historical": true/false,
        "backfill_supported": true/false
      },
      "tests": {
        "fetch_latest": {
          "status": "success/failed",
          "records_count": 7,
          "date_tested": "2026-01-13"
        },
        ...
      },
      "failure_modes": ["list of error types"],
      "earliest_success_date": "YYYY-MM-DD",
      "latest_success_date": "YYYY-MM-DD"
    }
  }
}
```

## Provider Scenarios

### Scenario A: Ideal Provider (HNX FTP PDF)
```
✓ fetch_latest       - Works
✓ fetch_yesterday    - Works
✓ fetch_historical   - Works (can get 2013 data!)
✓ backfill_supported - Full backfill possible
```
**Meaning**: Can backfill entire history from 2013 onwards

### Scenario B: Latest-Only Provider (HNX Yield Curve - likely)
```
✓ fetch_latest       - Works
✗ fetch_yesterday    - Fails
✗ fetch_historical   - Fails
✓ backfill_supported - Method exists but returns latest only
```
**Meaning**: Can only accumulate daily snapshots, not backfill history

### Scenario C: Fallback Provider (AsianBondsOnline)
```
✓ fetch_latest       - Works
✗ fetch_historical   - Expected (no historical API)
```
**Meaning**: Use for validation/latest data, not historical backfill

## Interpreting Results

### Good Signs
- ✓ fetch_historical = true → Can backfill from 2013!
- ✓ fetch_yesterday = true → At least some historical access
- records_count > 0 in tests → Provider is returning data

### Warning Signs
- ✗ fetch_latest = true → Provider may be down or blocking
- "403" in failure_modes → Being blocked (rate limiting or bot detection)
- "timeout" in failure_modes → Network issues or slow provider
- "parse_error" in failure_modes → Provider HTML structure changed

### Expected Limitations
- HNX Yield Curve: Likely "latest only" (no date picker on website)
- SBV Interbank: Likely "latest only" (no date range parameters)
- AsianBondsOnline: Expected "latest only" (fallback provider)
- HNX FTP PDF: Should support historical (file-based access)

## Next Steps After Probe

### If fetch_historical = true
**Action**: Proceed with historical backfill
```bash
# Backfill from 2013 to today
docker compose run --rm app python -m app.ingest backfill \
  --start 2013-01-01 \
  --end 2026-01-13 \
  --providers hnx_ftp_pdf
```

### If fetch_historical = false but fetch_latest = true
**Action**: Start daily accumulation now
```bash
# Run daily ingestion
docker compose run --rm app python -m app.ingest daily

# Or enable automatic daily updates
# Edit .env: SCHEDULER_ENABLED=true
# Restart: docker compose restart
```

Historical data will accumulate over time from the start date.

### If fetch_latest = false
**Action**: Investigate failure
1. Check `logs/ingest.log` for error details
2. Visit provider URL in browser to verify site is up
3. Check if being blocked (403 errors)
4. May need to adjust rate limiting or use Playwright

## Troubleshooting

### Probe hangs or times out
**Cause**: Provider is slow or blocking requests
**Fix**: Adjust rate limiting in `.env`:
```bash
RATE_LIMIT_SECONDS=2.0  # Increase from default 1.0
```

### All providers fail
**Cause**: Network connectivity issue
**Fix**:
1. Check internet connection
2. Try accessing provider URLs in browser
3. Check firewall settings

### "Permission denied" on reports/provider_probe.json
**Cause**: Directory doesn't exist
**Fix**:
```bash
mkdir -p reports
docker compose run --rm app python -m app.ingest probe
```

## Probe in CI/CD

For automated testing, add to your CI pipeline:

```bash
# Run probe and check results
docker compose run --rm app python -m app.ingest probe

# Verify critical providers work
python -c "
import json
with open('reports/provider_probe.json') as f:
    data = json.load(f)
    assert data['providers']['hnx_ftp_pdf']['capabilities']['fetch_historical'], 'HNX FTP should support historical'
"
```

## Summary

| Command | Purpose |
|---------|---------|
| `python -m app.ingest probe` | Test all providers |
| `python -m app.ingest probe --providers X` | Test specific providers |
| `cat reports/provider_probe.json` | View detailed results |
| Check Admin UI → Provider Status | Visual capability matrix |

**Key Takeaway**: The probe tells you what backfill strategy to use for each provider.
