# 🏦 Theo Dõi Lãi Suất - Dashboard Lãi Suất Ngân Hàng Việt Nam

Dashboard trực quan hóa lãi suất ngân hàng với **Liquid Glass UI**, cho phép so sánh, tra cứu lịch sử và tính toán tài chính.

---

## 🚀 Quick Start (5 Steps)

**Cài đặt**: Python 3.9+, Node.js 18+, SQLite 3

### 1️⃣ Backend - Khởi tạo DB & Crawl dữ liệu
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Khởi tạo database
python3 -m app.cli init-db

# (Optional) Crawl dữ liệu từ các nguồn
python3 -m app.cli scrape --all
```

### 2️⃣ Backend - Chạy FastAPI server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```
Backend chạy tại **http://localhost:8001**  
API Docs: **http://localhost:8001/docs**

### 3️⃣ Frontend - Cài đặt Next.js
```bash
cd frontend
npm install
cp .env.local.example .env.local
```

### 4️⃣ Frontend - Chạy dev server
```bash
npm run dev
```
Frontend chạy tại **http://localhost:3001**

**Note**: Dev output uses `frontend/.next-dev` (production build uses `frontend/.next`) to tránh dev asset 404 / kẹt “Đang tải…”.

### 5️⃣ Truy cập dashboard
Mở browser: **http://localhost:3001**

---

## 📋 Ports & Endpoints

- **Frontend**: http://localhost:3001
- **Backend API**: http://localhost:8001
- **Swagger Docs**: http://localhost:8001/docs

**Key endpoints**:
- `GET /health` - Health check
- `GET /meta/latest` - Metadata (scrape timestamps, record counts)
- `GET /latest?series_code=deposit_online&term_months=12` - Lãi suất mới nhất
- `GET /history?bank_name=VCB&series_code=deposit_online&term_months=12` - Lịch sử lãi suất

---

## 📚 Tài liệu chi tiết

### Data Semantics & Architecture
- **[DATA_SEMANTICS.md](DATA_SEMANTICS.md)** - Giải thích 2-layer architecture (raw vs canonical), source priority, per-day deduplication
- **[SCRAPING_SCHEDULE.md](SCRAPING_SCHEDULE.md)** - Scheduled scraping, cron jobs, monitoring alerts

### Migrations
Sử dụng migration runner chuẩn:
```bash
# Kiểm tra migration đã chạy
python3 -c "import sqlite3; conn = sqlite3.connect('data/rates.db'); cursor = conn.cursor(); cursor.execute('SELECT migration_name FROM schema_migrations'); print(cursor.fetchall())"

# Chạy migration (idempotent)
python3 -m app.migrations.run_migration phase2_2_1_rename_unique_index.sql
```

### Troubleshooting
**CSS intermittent loading**: Xem [CSS Stability Guide](frontend/CSS_STABILITY.md)  
**Migration errors**: Kiểm tra [DATA_SEMANTICS.md](DATA_SEMANTICS.md) → Migration History  
**Scraping failures**: Xem [SCRAPING_SCHEDULE.md](SCRAPING_SCHEDULE.md) → Troubleshooting

**Ops runbook**: Xem [docs/OPERATIONS.md](docs/OPERATIONS.md)

---

## 🏗️ Project Structure

```
Lai_suat/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── main.py         # FastAPI app
│   │   ├── db.py           # SQLite queries
│   │   ├── settings.py     # Config
│   │   └── migrations/     # SQL migrations
│   ├── tests/              # Pytest tests
│   └── requirements.txt
├── frontend/                # Next.js 15 frontend
│   ├── src/
│   │   ├── app/            # App Router pages
│   │   ├── components/     # React components
│   │   └── styles/
│   │       └── glass.css   # Liquid Glass theme
│   └── package.json
├── data/                    # SQLite DB (không commit)
└── app/                     # Scraper CLI tool
```

---

## 🧪 Quality Gates

**Backend**:
```bash
cd backend
pytest -q
python3 -m app.cli --help
```

**Frontend**:
```bash
cd frontend
npm run build  # Phải pass: Compiled successfully
```

---

## 🔄 Update Data

```bash
# Manual scrape
python3 -m app.cli scrape --all

# Automated (cron): Xem SCRAPING_SCHEDULE.md
```

---

## ⚙️ Environment Variables

**Backend** (`backend/.env`):
```bash
DB_PATH=../data/rates.db
CORS_ORIGINS=http://localhost:3001
HOST=0.0.0.0
PORT=8001
```

**Frontend** (`frontend/.env.local`):
```bash
NEXT_PUBLIC_API_BASE=http://localhost:8001
```

---

## 📄 License

MIT License

---

## 🤝 Contributing

1. Fork repo
2. Create feature branch
3. Run quality gates (`pytest`, `npm run build`)
4. Submit PR

---

**Documentation đầy đủ**: [DATA_SEMANTICS.md](DATA_SEMANTICS.md) | [SCRAPING_SCHEDULE.md](SCRAPING_SCHEDULE.md) | [frontend/CSS_STABILITY.md](frontend/CSS_STABILITY.md)
