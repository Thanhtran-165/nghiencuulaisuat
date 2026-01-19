# VN Bond Lab

**Vietnamese Bond Market Data Laboratory** - A comprehensive system for collecting, storing, and analyzing Vietnamese government bond yield curves and interbank interest rates.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![License](https://img.shields.io/badge/license-MIT-purple)

## Features

- **Automated Data Collection**: Fetches data from multiple sources (HNX, SBV, AsianBondsOnline)
- **Historical Backfill**: Supports backfilling data from 2013 onwards
- **Beautiful Web UI (Next.js)**: UI chính chạy trên `http://127.0.0.1:3002`
- **RESTful API**: Complete API for data access
- **Docker Support**: One-command deployment with Docker
- **Idempotent Operations**: Safe to run multiple times without duplicate data
- **Raw Data Storage**: Preserves original HTML/PDF files for audit purposes

## Quick Start (Local UI - khuyến nghị)

### Prerequisites

You need:
- Node.js + npm (for frontend)
- Python environment (for backend)

### 3 Steps to Run

1. **Open Terminal/Command Prompt** and navigate to the project directory:
   ```bash
   cd vn-bond-lab
   ```

2. **Start backend + frontend**:
   ```bash
   ./scripts/run_local_all.sh
   ```

3. **Open your browser** and go to:
   ```
   http://127.0.0.1:3002
   ```

Backend API/DB/ingest chạy ở `http://127.0.0.1:8001` (không dùng UI cũ nữa).

## Verification Checklist

After starting the application, verify it's working correctly:

```bash
# 1. Check health endpoint
curl http://127.0.0.1:8001/healthz
# Should return: {"status":"ok","timestamp":"..."}

# 2. Check readiness endpoint
curl http://127.0.0.1:8001/readyz
# Should return database and system status

# 3. Check metrics endpoint
curl http://127.0.0.1:8001/metrics | head
# Should return Prometheus-style metrics

# 4. Open Admin monitoring (Next.js)
open http://127.0.0.1:3002/admin/monitoring
```

If all checks pass, the application is ready for use!

## What You Can Do

### View Dashboard
Visit `http://127.0.0.1:3002` to see:
- Latest government bond yields (2Y, 5Y, 10Y)
- Yield curve spread (10Y-2Y)
- Overnight interbank rate
- Interactive charts

### View Yield Curves
Visit `http://127.0.0.1:3002/yield-curve` to:
- Select any date to view the yield curve
- See detailed yield data in a table
- Visualize the curve with an interactive chart

### View Interbank Rates
Visit `http://127.0.0.1:3002/interbank` to:
- View historical interbank rate trends
- Filter by tenor (ON, 1W, 1M, 3M, etc.)
- See rate movements over time

### Admin Panel
Visit `http://127.0.0.1:3002/admin/ingest` to:
- **Run Daily Ingestion**: Fetch the latest data from all sources
- **Backfill Data**: Fill in historical data for a date range
- **View Logs**: See recent ingestion runs and their status

## Collecting Data

### First Time Setup (Backfill)

1. Go to `http://127.0.0.1:3002/admin/ingest`
2. Under "Backfill Data", select:
   - **Start Date**: `2013-01-01` (or when you want to start)
   - **End Date**: Today's date
   - **Providers**: Select all providers (HNX Yield Curve, HNX FTP PDF, SBV Interbank, ABO)
3. Click "Run Backfill"
4. Wait for the process to complete (this may take a while for historical data)

### Daily Updates

You have two options:

**Option 1: Manual (Default)**
- Go to `http://127.0.0.1:3002/admin/ingest`
- Click "Run Daily Ingestion"
- Or use the Dashboard button "Cập nhật dữ liệu"
- Data will be fetched for today

**Option 2: Automatic (macOS LaunchAgent)**
Run (recommended for local macOS):
```bash
./scripts/install_launchagent_macos.sh
```
This will:
- Run once per day (default `18:05`, local time)
- Write DB/logs to `~/Library/Application Support/vn-bond-lab` (works even if repo is in iCloud Drive)
- Trigger `POST /api/admin/ingest/daily` if the backend is running, to avoid DuckDB file locks

Optional overrides:
```bash
DAILY_TIME=07:30 ./scripts/install_launchagent_macos.sh
PROVIDERS="hnx_yield_curve sbv_interbank lai_suat_rates" ./scripts/install_launchagent_macos.sh
```

## Documentation

- `QUICKSTART.md` - Quick start (Docker)
- `docs/DEPLOYMENT.md` - Deployment notes
- `docs/RUNBOOK_SMOKE.md` - Smoke/runbook checks
- `docs/GLOBAL_DATA.md` - Optional global data (FRED)
- `docs/AUDIT.md` - Audit notes and cleanup plan
- `docs/METRICS_MAP.md` - Metrics/data lineage map
- `docs/ACADEMIC_REVIEW.md` - Academic review (v1)
- `docs/INTERPRETATION_GUIDE.md` - How to interpret metrics
- `docs/REVIEW_AI2_SYNTHESIS.md` - Synthesis vs independent review (AI #2)
- `docs/MEMO_DATA_WAITING_FILL.md` - Memo: datasets waiting daily fill
- `docs/ACCEPTANCE_CHECKLIST.md` - Release readiness checklist
- `docs/history/README.md` - Archived phase docs

## Advanced Usage (for Developers)

### Project Structure

```
vn-bond-lab/
├── app/
│   ├── api/           # FastAPI routes
│   ├── db/            # Database schema and operations
│   ├── providers/     # Data providers (HNX, SBV, ABO)
│   ├── static/        # CSS and JavaScript
│   ├── templates/     # HTML templates
│   ├── config.py      # Configuration management
│   ├── ingest.py      # Ingestion pipeline CLI
│   └── main.py        # FastAPI application
├── data/
│   ├── duckdb/        # Database files (persisted)
│   └── raw/           # Raw HTML/PDF files (persisted)
├── tests/             # Test suite
├── logs/              # Application logs (persisted)
├── Dockerfile         # Docker image definition
├── docker-compose.yml # Docker orchestration
└── requirements.txt   # Python dependencies
```

### Running Tests

```bash
# Run all tests
docker compose run --rm app pytest

# Run specific test file
docker compose run --rm app pytest tests/test_database.py

# Run with coverage
docker compose run --rm app pytest --cov=app
```

### Using the CLI

```bash
# Run daily ingestion
docker compose run --rm app python -m app.ingest daily

# Backfill specific date range
docker compose run --rm app python -m app.ingest backfill \
  --start 2023-01-01 \
  --end 2023-12-31 \
  --providers hnx_yield_curve sbv_interbank

# Backfill specific providers
docker compose run --rm app python -m app.ingest backfill \
  --start 2023-01-01 \
  --end 2023-12-31 \
  --providers hnx_ftp_pdf
```

### Auto-ingest on macOS

To avoid forgetting daily data updates during local development:

```bash
./scripts/install_launchagent_macos.sh
```

It runs once per day (local time, default `18:05`) and updates all daily-capable providers (HNX + SBV; FRED if configured).

To enable global data (FRED) for BondY Stress comparisons:
- Set `FRED_API_KEY` in `.env` (see `.env.example`). `.env` is gitignored.

Override time/providers:

```bash
DAILY_TIME=07:30 PROVIDERS="hnx_trading sbv_interbank sbv_policy" ./scripts/install_launchagent_macos.sh
```

Logs:
- `~/Library/Application Support/vn-bond-lab/logs/local_ingest.log`
- `~/Library/Application Support/vn-bond-lab/logs/ingest.log`
- `~/Library/Application Support/vn-bond-lab/logs/launchd_ingest.out.log`
- `~/Library/Application Support/vn-bond-lab/logs/launchd_ingest.err.log`

DB location used by the LaunchAgent:
- `~/Library/Application Support/vn-bond-lab/bonds.duckdb`

To make the UI use the same DB:

```bash
export DB_PATH="$HOME/Library/Application Support/vn-bond-lab/bonds.duckdb"
export RAW_DATA_PATH="$HOME/Library/Application Support/vn-bond-lab/raw"
```

Uninstall:

```bash
./scripts/uninstall_launchagent_macos.sh
```

### API Endpoints

The application exposes a RESTful API:

- `GET /api/yield-curve/latest` - Get latest yield curve
- `GET /api/yield-curve?date=YYYY-MM-DD` - Get yield curve for specific date
- `GET /api/interbank/latest` - Get latest interbank rates
- `GET /api/interbank/timeseries?start_date=...&end_date=...&tenor=...` - Get historical interbank rates
- `GET /api/dashboard/metrics` - Get dashboard summary
- `GET /api/admin/ingest-runs` - Get recent ingestion runs
- `POST /api/admin/ingest/daily` - Trigger daily ingestion
- `POST /api/admin/ingest/backfill` - Trigger backfill

Example:
```bash
# Get latest yield curve
curl http://localhost:8000/api/yield-curve/latest

# Get yield curve for a specific date
curl http://localhost:8000/api/yield-curve?date=2024-01-15
```

### Database Schema

The application uses DuckDB with the following tables:

**gov_yield_curve**
- Government bond yield curve data by tenor
- Fields: date, tenor_label, tenor_days, spot_rate_continuous, par_yield, spot_rate_annual, source

**gov_yield_change_stats**
- Yield change statistics from HNX FTP PDF
- Fields: date, bucket_label, volume_domestic, volume_foreign, yield_min/max, source

**interbank_rates**
- Interbank interest rates
- Fields: date, tenor_label, rate, source

**ingest_runs**
- Ingestion run logs
- Fields: provider, start_date, end_date, status, rows_inserted, error_message, started_at, ended_at

### Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Application
APP_NAME=vn-bond-lab
DEBUG=false
LOG_LEVEL=INFO

# Server
HOST=0.0.0.0
PORT=8000

# Database
DB_PATH=/app/data/duckdb/bonds.duckdb

# Data Collection
START_DATE_DEFAULT=2013-01-01
RATE_LIMIT_SECONDS=1.0
MAX_RETRIES=3

# Scheduler
SCHEDULER_ENABLED=false
SCHEDULER_DAILY_TIME=18:05
SCHEDULER_TIMEZONE=Asia/Ho_Chi_Minh

# Raw Data Storage
ENABLE_RAW_STORAGE=true
```

## Data Sources

### HNX (Hanoi Stock Exchange)
- **Yield Curve**: https://hnx.vn/trai-phieu/duong-cong-loi-suat.html
- **FTP PDF Statistics**: Daily PDF files with yield change statistics
- **Coverage**: 2013 onwards (yield curve reference implementation)

### SBV (State Bank of Vietnam)
- **Interbank Rates**: https://www.sbv.gov.vn/webcenter/portal/m/menu/trangchu/ls/lsttlnh
- **Coverage**: Latest data (accumulated over time)

### AsianBondsOnline (ADB)
- **Market Watch**: https://asianbondsonline.adb.org/vietnam/
- **Coverage**: Latest data (2Y, 5Y, 10Y government bonds + VNIBOR)

## Troubleshooting

### Port Already in Use
If port 8000 is already in use, edit `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"  # Change 8000 to another port
```

### Database Errors
The database is automatically initialized on first run. If you encounter errors:
```bash
# Reset everything (CAUTION: deletes all data)
docker compose down -v
docker compose up --build
```

### Provider Timeouts
Some providers may be slow or block requests. The system will:
- Retry automatically (up to 3 times by default)
- Log errors but continue with other providers
- Store raw data for debugging

### Out of Memory
If you encounter memory issues during backfill:
1. Process shorter date ranges
2. Reduce `MAX_CONCURRENT_REQUESTS` in `.env`
3. Run backfill for one provider at a time

## Development

### Local Development (without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Set up environment
cp .env.example .env

# Run database initialization
export STATE_DIR="$HOME/Library/Application Support/vn-bond-lab"
export DB_PATH="$STATE_DIR/bonds.duckdb"
export RAW_DATA_PATH="$STATE_DIR/raw"
python -c "from app.db.schema import DatabaseManager; db = DatabaseManager('${DB_PATH}'); db.connect(); db.initialize_schema()"

# Run application
uvicorn app.main:app --reload
```

### Adding New Providers

1. Create a new provider class in `app/providers/`:
   ```python
   from app.providers.base import BaseProvider

   class MyProvider(BaseProvider):
       def fetch(self, target_date):
           # Implement data fetching logic
           pass

       def backfill(self, start_date, end_date):
           # Implement backfill logic
           pass
   ```

2. Register in `app/ingest.py`:
   ```python
   PROVIDERS = {
       'my_provider': MyProvider,
       # ... existing providers
   }
   ```

## Performance Considerations

- **Rate Limiting**: Default 1 second between requests (adjustable via `RATE_LIMIT_SECONDS`)
- **Concurrent Requests**: Maximum 3 concurrent requests (adjustable via `MAX_CONCURRENT_REQUESTS`)
- **Timeout**: 30 seconds per request (adjustable via `REQUEST_TIMEOUT`)
- **Backfill Strategy**: Start with recent data, then progressively backfill older periods

## License

MIT License. See `LICENSE`.

## Credits

Built with:
- FastAPI - Modern Python web framework
- DuckDB - In-process SQL database
- Playwright - Headless browser automation
- Chart.js - JavaScript charting library
- Tailwind CSS - Utility-first CSS framework (liquid glass design)

## Support

For issues, questions, or contributions:
1. Check the logs in `logs/ingest.log`
2. Review the Admin Panel at `/admin/ingest`
3. Open an issue on GitHub (if applicable)

---

**Note**: This system is designed for educational and research purposes. While we strive for accuracy, always verify critical data with official sources.
