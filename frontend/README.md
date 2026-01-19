# Frontend - VN Bond Lab (Next.js)

Next.js frontend với UI “Liquid Glass” cho VN Bond Lab.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Configure environment:
Tạo `.env.local` (hoặc copy từ `.env.local.example`) với:
```env
BACKEND_URL=http://localhost:8001
```

3. Run the development server:
```bash
npm run dev
```

Ứng dụng chạy tại `http://localhost:3002` (hoặc port khác nếu set `FRONTEND_PORT` khi chạy script)

Backend FastAPI (Bond Lab) chạy tại `http://localhost:8001`

## Start/Stop nhanh (khuyến nghị)

Từ thư mục `Bond Lab/vn-bond-lab`:

- Start tất cả: `./scripts/run_local_all.sh`
- Stop tất cả: `./scripts/stop_local_all.sh`

Frontend port mặc định `3002`. Đổi port:

- `FRONTEND_PORT=3005 ./scripts/run_local_frontend.sh`

### Dev guardrails (anti “Đang tải…”)
- Dev output is isolated to `.next-dev` (production build uses `.next`), so `npm run build` won’t clobber dev assets.
- `npm run dev` stops any existing `next dev` for this project before starting.
- If anything looks weird: `npm run dev:clean`

## Features

- **Dashboard**: Tổng quan nhanh
- **Nhận định**: 3 thời hạn (ngắn/trung/dài) gọi API `GET /api/insights/horizons`
- **Lãi suất**: UI lãi suất (port từ dự án Lai_suat) nằm tại `/lai-suat`
- **Proxy API**: Next.js rewrite `/api/* -> BACKEND_URL/api/*` để tránh CORS khi dev

## Build

Create a production build:
```bash
npm run build
```

Start the production server:
```bash
npm start
```

## Components

- `GlassCard`: Glass-effect card component
- `TopTabs`: Tabs cho khu vực Lãi suất
