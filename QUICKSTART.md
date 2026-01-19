# Quick Start Guide - VN Bond Lab

## ✅ UI chính: Next.js (port 3002)

- **Frontend (Next.js, UI cuối cùng):** `http://127.0.0.1:3002`
- **Backend (FastAPI, API/DB/ingest):** `http://127.0.0.1:8001`
- UI Jinja cũ trên backend **đã redirect** về Next.js (mặc định).

## 🚀 Chạy local (khuyến nghị)

### 1. Navigate to Project
```bash
cd vn-bond-lab
```

### 2. Start (One Command)
```bash
./scripts/run_local_all.sh
```

### Nếu bạn từng chạy backfill trước đây (repo `.local-data`)
Nếu UI báo dữ liệu “mỏng” dù bạn nhớ đã backfill lịch sử, nhiều khả năng có 2 file DuckDB:
- Repo: `vn-bond-lab/.local-data/bonds.duckdb` (cũ, không dùng nữa)
- State dir: `~/Library/Application Support/vn-bond-lab/bonds.duckdb` (chuẩn cho local)

Để chuyển dữ liệu lịch sử sang DB mới (khuyến nghị), chạy:
```bash
./scripts/migrate_repo_db_to_state_dir.sh
```

### 3. Open Browser
```
http://127.0.0.1:3002
```

## 📊 What You Get

### 🎯 Dashboard (`/`) — tổng quan nhanh
- Latest government bond yields (2Y, 5Y, 10Y)
- Yield curve spread (10Y-2Y)
- Overnight interbank rate
- Interbank snapshot (hôm nay vs hôm qua)

### 📈 Yield Curve Viewer (`/yield-curve`)
- Select any date
- View yield curve by tenor
- See detailed data table

### 💱 Interbank Rates (`/interbank`)
- Historical rate trends
- Filter by tenor (ON, 1W, 1M, 3M...)
- Time-series visualization

### 🧠 Nhận định (`/nhan-dinh`)
- 3 thời hạn (ngắn/trung/dài) theo spec “phiên” + readiness + evidence (information-only)

### ⚙️ Admin (`/admin`) + subpages
- `/admin/ingest`: daily ingest / backfill / probe + ingest runs
- `/admin/lai-suat`: scrape + sync `bank_rates` + log tail
- `/admin/alerts`: thresholds
- `/admin/monitoring`: SLO / drift
- `/admin/quality`: DQ runs

### 💳 Lãi suất (`/lai-suat`)
- Hôm nay / Lịch sử / So sánh / Máy tính (dùng dữ liệu `bank_rates`)

## 🗂️ Complete Project Structure

```
vn-bond-lab/
├── app/
│   ├── api/
│   │   └── routes.py                  # REST API endpoints
│   ├── db/
│   │   └── schema.py                  # DuckDB schema & operations
│   ├── providers/
│   │   ├── base.py                    # Base provider class
│   │   ├── hnx_yield_curve.py         # HNX yield curve scraper
│   │   ├── hnx_ftp_pdf.py             # HNX PDF parser
│   │   ├── sbv_interbank.py           # SBV interbank scraper
│   │   └── abo_market_watch.py        # AsianBondsOnline scraper
│   ├── static/
│   │   └── css/
│   │       └── styles.css             # Liquid glass styles
│   ├── templates/                     # Legacy Jinja UI (redirected by default)
│   ├── config.py                      # Configuration management
│   ├── ingest.py                      # Ingestion pipeline CLI
│   └── main.py                        # FastAPI application
├── tests/
│   ├── conftest.py                    # Test fixtures
│   ├── test_database.py               # Database tests
│   └── test_providers.py              # Provider tests
├── data/                              # Persistent data (created at runtime)
│   ├── duckdb/                        # Database files
│   └── raw/                           # Raw HTML/PDF files
├── logs/                              # Application logs
├── frontend/                          # Next.js UI (port 3002)
├── .env.example                       # Environment variables template
├── .gitignore                         # Git ignore rules
├── docker-compose.yml                 # Docker orchestration
├── Dockerfile                         # Docker image
├── entrypoint.sh                      # Container entrypoint
├── requirements.txt                   # Python dependencies
├── pytest.ini                         # Test configuration
├── README.md                          # Full documentation
└── QUICKSTART.md                      # This file
```

## 🔧 Key Features

### Data Providers
- ✅ HNX Yield Curve (government bond yields by tenor)
- ✅ HNX FTP PDF (yield change statistics)
- ✅ SBV Interbank (interbank interest rates)
- ✅ AsianBondsOnline (market data fallback)
- ✅ Lai_suat (bank deposit/loan rates from local SQLite)

### Database (DuckDB)
- ✅ `gov_yield_curve` - Government bond yields
- ✅ `gov_yield_change_stats` - Yield statistics
- ✅ `interbank_rates` - Interbank rates
- ✅ `bank_rates` - Bank deposit/loan rates
- ✅ `ingest_runs` - Operation logs

### API Endpoints
- ✅ `/api/yield-curve/latest` - Latest yield curve
- ✅ `/api/yield-curve?date=YYYY-MM-DD` - Historical yield curve
- ✅ `/api/interbank/latest` - Latest interbank rates
- ✅ `/api/interbank/timeseries` - Historical interbank rates
- ✅ `/api/dashboard/metrics` - Dashboard metrics
- ✅ `/api/admin/ingest-runs` - Ingestion logs
- ✅ `/api/admin/ingest/daily` - Trigger daily collection
- ✅ `/api/admin/ingest/backfill` - Trigger backfill
- ✅ `/api/bank-rates/latest` - Latest bank rates
- ✅ `/api/bank-rates/history` - Bank rate history (by bank + series + term)

### CLI Commands
```bash
# Daily ingestion
docker compose run --rm app python -m app.ingest daily

# Backfill date range
docker compose run --rm app python -m app.ingest backfill \
  --start 2023-01-01 --end 2023-12-31

# Specific providers
docker compose run --rm app python -m app.ingest backfill \
  --start 2023-01-01 --end 2023-12-31 \
  --providers hnx_yield_curve sbv_interbank
```

## 🧰 Auto-ingest on macOS (daily updates)

If you run the app locally on macOS and want data to keep updating automatically, install the LaunchAgent:

```bash
./scripts/install_launchagent_macos.sh
```

It runs once per day (local time, default `18:05`) and updates all daily-capable providers (HNX + SBV; FRED if configured).
Lãi suất (Lai_suat) cũng được đồng bộ mỗi ngày vào DB chung.

To enable global data (FRED) for BondY Stress comparisons:
- Set `FRED_API_KEY` in `.env` (see `.env.example`). `.env` is gitignored.
Override time/providers:

```bash
DAILY_TIME=07:30 PROVIDERS="hnx_trading sbv_interbank sbv_policy" ./scripts/install_launchagent_macos.sh
```

Note: If your repo lives in iCloud Drive (“Mobile Documents”), macOS background jobs may not be allowed to write there.
So the LaunchAgent writes DB/logs to:
- `~/Library/Application Support/vn-bond-lab`

To make the UI use the same DB, start the server with:

```bash
export DB_PATH="$HOME/Library/Application Support/vn-bond-lab/bonds.duckdb"
export RAW_DATA_PATH="$HOME/Library/Application Support/vn-bond-lab/raw"
```

Logs:
- `~/Library/Application Support/vn-bond-lab/logs/local_ingest.log`
- `~/Library/Application Support/vn-bond-lab/logs/ingest.log`
- `~/Library/Application Support/vn-bond-lab/logs/launchd_ingest.out.log`
- `~/Library/Application Support/vn-bond-lab/logs/launchd_ingest.err.log`

Uninstall:

```bash
./scripts/uninstall_launchagent_macos.sh
```

## 🎨 Liquid Glass Design

The UI features:
- Glassmorphism with backdrop blur
- Gradient backgrounds (navy/indigo/purple)
- Subtle glows and shadows
- Responsive design
- Interactive Chart.js visualizations

## 📝 Configuration

Edit `.env` file (copy from `.env.example`):

```bash
# Scheduler (automatic daily updates)
SCHEDULER_ENABLED=true
SCHEDULER_DAILY_TIME=18:05
SCHEDULER_TIMEZONE=Asia/Ho_Chi_Minh

# Rate limiting
RATE_LIMIT_SECONDS=1.0
MAX_CONCURRENT_REQUESTS=3

# Raw data storage
ENABLE_RAW_STORAGE=true
```

## 🧪 Testing

```bash
# Run all tests
docker compose run --rm app pytest

# Run specific tests
docker compose run --rm app pytest tests/test_database.py
```

## 🛑 Stopping the Application

```bash
# Stop
docker compose down

# Stop and remove all data (CAUTION!)
docker compose down -v
```

## 📖 Full Documentation

See `README.md` for comprehensive documentation.

## ⚡ Performance Tips

1. **Start small**: Backfill recent data first (last 6 months)
2. **Progressive backfill**: Then backfill older periods
3. **Provider-specific**: Run one provider at a time if needed
4. **Rate limiting**: Adjust `RATE_LIMIT_SECONDS` if blocked
5. **Monitor logs**: Check `/admin/ingest` for progress

## 🐛 Troubleshooting

**Port 8000 already in use?**
Edit `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"  # Use different port
```

**Database errors?**
```bash
docker compose down -v  # Reset everything
docker compose up --build
```

**Providers timing out?**
- System will retry automatically (3 times)
- Other providers continue running
- Check raw data in `data/raw/` for debugging

## 🎯 Next Steps

1. ✅ Start the application
2. ✅ Explore the dashboard
3. ✅ Run your first backfill (Admin Panel)
4. ✅ Set up daily automatic updates (optional)
5. ✅ Explore the API endpoints

---

**Need help?** Check `README.md` or logs in `logs/ingest.log`
