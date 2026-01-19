# 🏦 Bank Interest Rate Dashboard - Full Stack

Dashboard trực quan hóa lãi suất ngân hàng Việt Nam với **Liquid Glass UI**, cho phép so sánh, tra cứu lịch sử và tính toán tài chính.

---

## 🎯 Features

### Dashboard Pages
- **[/](http://localhost:3001)** - **Hôm nay**: Tổng quan lãi suất cao nhất, bảng tổng hợp tiền gửi/khoản vay
- **[/lich-su](http://localhost:3001/lich-su)** - **Lịch sử**: Biểu đồ xu hướng lãi suất theo thời gian
- **[/so-sanh](http://localhost:3001/so-sanh)** - **So sánh**: So sánh Online vs Tại quầy, Thế chấp vs Tín chấp
- **[/may-tinh](http://localhost:3001/may-tinh)** - **Máy tính**: Máy tính tài chính (vay/tiền gửi) với chuẩn Actual/365

### UI/UX Highlights
- ✨ **Liquid Glass Theme**: Glassmorphism với blur effects, transparency, gradient backgrounds
- 🌐 **Full Vietnamese Localization**: Toàn bộ UI tiếng Việt
- 📊 **Interactive Charts**: Recharts visualization với responsive design
- 🧮 **Financial Calculators**:
  - Máy tính khoản vay: 3 phương thức (Gốc đều, Annuity, Chỉ trả lãi)
  - Máy tính tiền gửi: 5 phương thức trả lãi, hỗ trợ rút trước hạn
  - **NEW**: Chọn lãi suất từ dữ liệu ngân hàng thực tế
- 🔄 **Real-time Data**: Fetch từ FastAPI backend với caching và abort controller

---

## 🚀 Quick Start (5 Steps)

### Prerequisites
- Python 3.9+
- Node.js 18+
- SQLite 3

### Step 1: Clone & Setup Database
```bash
# Navigate to project
cd Lai_suat

# Initialize SQLite database
python3 -m app.cli init-db

# Scrape initial data (optional - takes a few minutes)
python3 -m app.cli scrape --all
```

### Step 2: Backend (FastAPI)
```bash
cd backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # MacOS/Linux
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file (copy from .env.example)
cp .env.example .env
# Edit .env if needed (DB_PATH, CORS_ORIGINS, PORT)

# Run backend
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Backend will run at **http://localhost:8001**
API Docs: **http://localhost:8001/docs**

### Step 3: Frontend (Next.js)
```bash
cd frontend

# Install dependencies
npm install

# Create .env.local file
cp .env.local.example .env.local
# Edit NEXT_PUBLIC_API_BASE if backend runs on different port

# Run frontend
npm run dev
```

Frontend will run at **http://localhost:3001**

### Step 4: Access Dashboard
Open browser: **http://localhost:3001**

### Step 5: (Optional) Update Data
```bash
# From project root
python3 -m app.cli scrape --all
```

---

## 📂 Project Structure

```
Lai_suat/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── main.py         # FastAPI app entry point
│   │   ├── db.py           # SQLite queries
│   │   ├── schemas.py      # Pydantic models
│   │   └── settings.py     # Config with Pydantic Settings
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── frontend/                # Next.js 15 frontend
│   ├── src/
│   │   ├── app/            # App Router pages
│   │   │   ├── layout.tsx  # Root layout (imports globals.css)
│   │   │   ├── globals.css # Imports glass.css
│   │   │   ├── page.tsx    # / (Hôm nay)
│   │   │   ├── lich-su/    # /lich-su (Lịch sử)
│   │   │   ├── so-sanh/    # /so-sanh (So sánh)
│   │   │   └── may-tinh/   # /may-tinh (Máy tính)
│   │   ├── components/     # React components
│   │   │   ├── GlassCard.tsx
│   │   │   ├── TopTabs.tsx
│   │   │   ├── RateSourceSelector.tsx  # NEW: Bank rate selector
│   │   │   ├── LoanCalculator.tsx
│   │   │   ├── DepositCalculator.tsx
│   │   │   └── ...charts, tables
│   │   ├── lib/
│   │   │   ├── api.ts      # API client
│   │   │   ├── calculators/  # Financial calculation logic
│   │   │   └── utils.ts
│   │   └── styles/
│   │       └── glass.css   # Liquid Glass theme
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── .env.local.example
│   └── README.md
├── app/                     # Python scraper (CLI tool)
│   ├── cli.py              # CLI entry point
│   ├── db.py               # Database schema & queries
│   ├── ingest.py           # Data ingestion logic
│   ├── scraper.py          # Web scraper (strategies A/B)
│   ├── utils.py            # Utilities
│   └── parsers/            # Deposit/Loan parsers
├── tests/                  # Pytest tests
├── data/                   # SQLite database
│   └── rates.db           # NOT committed (init via CLI)
├── .gitignore
└── README.md
```

---

## 🔧 API Endpoints

Backend exposes RESTful API at `http://localhost:8001`:

### Health & Meta
- `GET /health` - Health check
- `GET /meta/latest` - Latest metadata (scraped timestamps, counts)

### Reference Data
- `GET /banks` - List all banks
- `GET /series` - List all series (deposit_tai_quay, deposit_online, loan_the_chap, loan_tin_chap)

### Rates Data
- `GET /latest` - Get latest rates
  - Query: `series_code` (required), `term_months` (deposit only), `sort` (rate_desc/rate_asc)
  - Returns: Latest observations per bank
- `GET /history` - Get historical rates
  - Query: `bank_name`, `series_code`, `term_months` (optional), `limit` (optional)
  - Returns: Time series for a specific bank

Full API documentation: **http://localhost:8001/docs** (Swagger UI)

---

## 🎨 UI Architecture & Troubleshooting

### Tech Stack
- **Frontend**: Next.js 15 (App Router), TypeScript, TailwindCSS, Recharts
- **Backend**: FastAPI, Pydantic, SQLite
- **Styling**: Custom Liquid Glass theme with glassmorphism effects

### Common Issue: "Mất Tailwind Style" (CSS Not Loading)

**Symptoms**: UI render như HTML thô, không có glass effects, background trắng.

**Root Cause**: CSS pipeline bị broken (wrong import path, missing directives, incorrect content globs).

**Fix Checklist**:
1. ✅ **Verify layout.tsx imports globals.css**:
   ```typescript
   // frontend/src/app/layout.tsx
   import "./globals.css";  // MUST be relative import, NOT @/styles/glass.css
   ```

2. ✅ **Verify globals.css exists and imports glass.css**:
   ```css
   /* frontend/src/app/globals.css */
   @import "../styles/glass.css";
   ```

3. ✅ **Verify glass.css has @tailwind directives**:
   ```css
   /* frontend/src/styles/glass.css */
   @tailwind base;
   @tailwind components;
   @tailwind utilities;
   /* ... rest of Liquid Glass theme */
   ```

4. ✅ **Verify tailwind.config.ts content globs**:
   ```typescript
   // frontend/tailwind.config.ts
   content: [
     "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
     "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
     "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
     "./src/styles/**/*.{js,ts,jsx,tsx,mdx,css}",  // IMPORTANT
   ]
   ```

5. ✅ **Check for pages router conflict**:
   - Ensure NO `frontend/pages/` directory exists
   - Only use App Router (`frontend/src/app/`)

6. ✅ **Clear cache and rebuild**:
   ```bash
   cd frontend
   rm -rf .next
   npm run build  # Should compile without errors
   npm run dev
   ```

**If still broken**: Check browser DevTools Console for CSS import errors, verify file paths match actual structure.

---

## 🧮 Financial Calculator Logic

### Loan Calculator (Máy tính khoản vay)
- **Payment Methods**:
  - **Gốc đều (Principal Equal)**: Principal payment constant, interest decreases
  - **Annuity (EMI)**: Equal monthly payments
  - **Chỉ trả lãi (Interest Only)**: Interest only, principal at end
- **Day Count Convention**:
  - **Actual/365** (Vietnam banking standard): Interest = outstanding × annualRate/100 × days_in_period / 365
  - **r/12** (Approximation): Monthly rate = annualRate / 12
- **Grace Period**: Support for grace principal months
- **Rate Source**: Manual input OR select from bank data

### Deposit Calculator (Máy tính tiền gửi)
- **Interest Payment Methods**:
  - Cuối kỳ (End of term)
  - Hàng tháng (Monthly)
  - Hàng quý (Quarterly)
  - Chiết khấu (Discounted)
  - Gép kép (Compound)
- **Early Withdrawal**: Calculate penalty interest at non-term rate
- **Day Count**: Same Actual/365 or r/12 options

---

## 🌐 Vietnamese Localization

All UI text is in Vietnamese:
- Navigation: Hôm nay, Lịch sử, So sánh, Máy tính
- Date format: dd/mm/yyyy (e.g., 05/01/2026)
- Currency format: VND with thousand separators (e.g., 100.000.000 ₫)
- Percentage: 2 decimal places (e.g., 6,50%)

---

## 🔄 Automated Scraping & Monitoring

### Check System Status

Check the latest scrape status via API:
```bash
# Health check
curl http://localhost:8001/health

# Detailed metadata
curl http://localhost:8001/meta/latest
```

Response example:
```json
{
  "scraped_at_by_url": {
    "https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/": "2026-01-05T13:46:55Z",
    "https://timo.vn/blogs/so-sanh-lai-suat-vay-ngan-hang-cap-nhat-moi-nhat/": "2026-01-05T13:46:55Z"
  },
  "latest_scraped_at": "2026-01-05T13:46:55Z",
  "sources_count": 2,
  "observations_count": 287,
  "last_anomaly": null
}
```

### Setup Automated Scraping (Cron)

For production, set up automated scraping using cron:

**Quick Start**:
```bash
# 1. Make script executable
chmod +x scripts/run_scrape_job.sh

# 2. Test run manually
./scripts/run_scrape_job.sh 0.30

# 3. Add to cron (every 6 hours)
crontab -e
# Add this line:
0 */6 * * * cd /path/to/Lai_suat && ./scripts/run_scrape_job.sh >> logs/scrape_cron.log 2>&1
```

**Full Documentation**: See [docs/cron.md](docs/cron.md) for:
- Exit codes (0=success, 2=anomaly, 3=fatal)
- Log rotation strategies
- Troubleshooting tips
- Advanced monitoring setups

### Monitoring Best Practices

1. **Check Health**: Use `/health` endpoint for quick health check
2. **Check Metadata**: Use `/meta/latest` for detailed scrape status
3. **Review Logs**: Check `logs/scrape_*.log` for anomalies
4. **Exit Code 2**: Warning - data dropped significantly, needs review
5. **Exit Code 3**: Error - scraping failed, retry manually

---

## 📊 Database Schema

### Key Tables
- **sources**: Scraping metadata (URL, timestamp, content hash, strategy)
- **banks**: Bank list (id, name)
- **series**: Product series (deposit_tai_quay, deposit_online, loan_the_chap, loan_tin_chap)
- **terms**: Term labels (1, 3, 6, 12, 18, 24, 36 months)
- **observations**: Rate observations (bank_id, series_id, term_id, rate_pct/rate_min_pct/rate_max_pct)

### Views
- **v_latest_source_per_url**: Latest source per URL
- **v_latest_observations**: Latest observations per bank/series/term (used by API)

Full schema documentation: See original README sections below.

---

## 🐍 Python CLI Scraper (Original Tool)

### Usage
```bash
# Initialize database
python3 -m app.cli init-db

# Scrape all URLs
python3 -m app.cli scrape --all

# Export data
python3 -m app.cli export --db data/rates.db --latest --out out/
```

### Features
- **Dual Strategy Scraping**: Table/Header + Regex/Keyword with auto-fallback
- **Change Detection**: Content hash-based, only store if changed
- **Anomaly Detection**: Alert if record count drops >30% from previous scrape
- **Export Formats**: Long, wide (pivot by term), loan-specific

See original README below for detailed scraper documentation.

---

## 🛠️ Development

### Backend Development
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### Frontend Development
```bash
cd frontend
npm run dev
# Runs on http://localhost:3001
npm run build  # Production build
npm run lint   # ESLint
```

### Quality Gates
```bash
# Frontend
cd frontend
npm run build  # Must pass: Compiled successfully, Linting and checking validity of types

# Backend
cd backend
python -m py_compile app/*.py  # Import check
# Tests (if available)
pytest tests/
```

---

## 📝 Configuration Files

### Environment Variables

**Backend (.env)**:
```bash
DB_PATH=../data/rates.db
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
HOST=0.0.0.0
PORT=8001
```

**Frontend (.env.local)**:
```bash
NEXT_PUBLIC_API_BASE=http://localhost:8001
```

### Git Strategy
- **Database**: `data/rates.db` NOT committed (too large, changes frequently)
  - Init via: `python3 -m app.cli init-db`
  - Populate via: `python3 -m app.cli scrape --all`
- **Dependencies**: `node_modules/`, `.venv/` ignored
- **Build artifacts**: `.next/`, `dist/`, `__pycache__/` ignored
- **Secrets**: `.env`, `.env.local` ignored (use `.env.example` as template)

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run quality gates (build, lint, tests)
5. Submit a pull request

---

## 📞 Support

For issues or questions:
- Check troubleshooting section above
- Review API docs at http://localhost:8001/docs
- Open an issue on GitHub

---

## Original Documentation (Scraper)

<details>
<summary>Click to expand original Python scraper documentation</summary>

### Database Schema (Original)
[Full schema details from original README]

### Scraping Strategies
**Strategy A — Table/Header (ưu tiên)**: Parse <table> elements
**Strategy B — Regex/Keyword (fallback)**: Text-based extraction with regex

### Anomaly Detection
- Default threshold: 30% drop in record count
- Exit code 2: Anomaly detected
- Exit code 3: Fatal scrape failure

### Export Formats
- `out/long.csv`: 1 row/observation
- `out/wide_deposit.csv`: Pivot by term
- `out/loan.csv`: Loan-specific format

</details>
