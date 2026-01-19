# Ghi chú vận hành (Runbook)

## Mục tiêu
- Tránh lỗi frontend kẹt `Đang tải...` do asset dev 404.
- Chuẩn hoá cách chạy dev/build để giảm rủi ro gần 0%.

## Kiến trúc nhanh
- **Backend**: FastAPI (port `8001`) + SQLite (`data/rates.db`)
- **Frontend**: Next.js (port `3001`)

## Chạy backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# init DB (idempotent)
python3 -m app.cli init-db

# chạy API
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## Chạy frontend (DEV)
```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

### Guardrails đã bật sẵn
- Dev output **không dùng** `.next` nữa, mà dùng `.next-dev` để tránh `next build` ghi đè dev cache.
- `npm run dev` tự **dừng** `next dev` đang chạy của **chính project này** trước khi start.
- `npm run dev:clean` xoá **`.next-dev`** rồi start lại.

## Build frontend (PROD)
```bash
cd frontend
npm run build
npm start
```

## Các “không nên”
- Không chạy `next dev` trực tiếp (bypass guardrails). Luôn dùng `npm run dev`.
- Không xoá `.next-dev`/`.next` thủ công khi dev server đang chạy.
- Không chạy nhiều instance `next dev` cùng project.

## Check nhanh khi nghi ngờ bị “kẹt Đang tải...”
1) Frontend asset dev phải trả `200`:
```bash
curl -I http://localhost:3001/_next/static/css/app/layout.css | head
curl -I http://localhost:3001/_next/static/chunks/main-app.js | head
curl -I http://localhost:3001/_next/static/chunks/app/page.js | head
```

2) Backend phải OK:
```bash
curl http://localhost:8001/health
curl http://localhost:8001/series | python3 -m json.tool
```

## Troubleshooting chuẩn
- Frontend load nhưng UI kẹt/không style: `cd frontend && npm run dev:clean`
- Backend báo thiếu series_code (ví dụ `deposit_online`): restart backend (startup sẽ seed series tự động).

