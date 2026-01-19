# Ghi chú phát hành - Phiên bản 1.0.0

**Ngày phát hành**: 2026-01-19  
**Phiên bản**: 1.0.0

---

## Tổng quan

VN Bond Lab v1.0.0 là bản phát hành công khai đầu tiên. Dự án cung cấp hệ thống thu thập, lưu trữ và phân tích dữ liệu thị trường trái phiếu Chính phủ Việt Nam, kèm theo quan sát vận hành (observability), giám sát (monitoring) và công cụ vận hành (ops).

Ghi chú phát hành tiếng Anh: `RELEASE_NOTES.md`.

---

## Điểm nổi bật

### Tính năng sẵn sàng vận hành

- **Observability & Monitoring**
  - `/healthz` – kiểm tra sống (liveness) nhanh
  - `/readyz` – kiểm tra sẵn sàng (readiness) gồm DB/schema
  - `/metrics` – metrics kiểu Prometheus
  - `/api/version` – phiên bản + feature flags
  - Trang monitoring: `/admin/monitoring`

- **Công cụ vận hành**
  - Script smoke test: `scripts/rc_smoke.sh`
  - Backup/restore dữ liệu
  - Demo mode với dữ liệu synthetic để test nhanh
  - Tài liệu upgrade/rollback

- **Data Quality**
  - Framework DQ (PASS/WARN/ERROR) + rule engine
  - Quản lý ngưỡng cảnh báo (alert thresholds)
  - Theo dõi độ tin cậy provider + drift detection
  - SLO metrics (tỉ lệ thành công theo thời gian)

### Bảo mật & an toàn

- Hỗ trợ Basic Auth cho các admin endpoints (`ADMIN_AUTH_*`)
- Tự động che (redact) secrets trong logs
- Demo mode giúp tránh trộn dữ liệu thật/giả trong quá trình thử nghiệm

### Phân tích & báo cáo

- Transmission analytics (tác động policy rate lên yield)
- Stress model (BondY scenarios)
- Vietnamese daily snapshot
- Tạo báo cáo PDF theo ngày

---

## Tình trạng dữ liệu (quan trọng)

Một số dataset **không backfill được** (nguồn chỉ cung cấp “latest”), nên cần chạy ingest theo ngày để dữ liệu tích luỹ dần:

- SBV interbank (`interbank_rates`) – “latest only”
- SBV policy (`policy_rates`) – thường “current/announcement”, khó backfill lịch sử
- ABO Market Watch – chỉ dùng đối chiếu ngắn hạn, không lấp lịch sử
- Secondary trading (`gov_secondary_trading`) – lịch sử bị giới hạn bởi endpoint (earliest hiện ~2025-01-15)

Chi tiết và ảnh hưởng học thuật: `docs/MEMO_DATA_WAITING_FILL.md`.

---

## Thay đổi phá vỡ (Breaking Changes)

Không có.

---

## Thay đổi cấu hình

### Biến môi trường (Environment Variables)

```bash
# Observability
LOG_FORMAT=text  # "text" hoặc "json"

# Admin Authentication (chuẩn - Phase 8.1)
ADMIN_AUTH_ENABLED=false
ADMIN_USER=admin
ADMIN_PASSWORD=change_me

# Deprecated (Phase 8.1): BASIC_AUTH_* → tự map sang ADMIN_AUTH_*

# Demo Mode (Phase 9)
DEMO_MODE=false
DEMO_DB_PATH=data/demo.db
OVERRIDE_DEMO_INGEST=false

# Metrics Authentication (Phase 8)
METRICS_AUTH_ENABLED=false
```

### Migration

Schema migrations chạy tự động khi khởi động và có tính idempotent (chạy nhiều lần vẫn an toàn).

---

## Hướng dẫn nâng cấp

```bash
# 1. Backup dữ liệu
docker compose exec -T app python -m app.ops backup

# 2. Cập nhật code
git pull origin main

# 3. Cập nhật cấu hình
cp .env.example .env
nano .env

# 4. Rebuild và chạy lại
docker compose -f docker-compose.prod.yml up -d --build

# 5. Smoke test
bash scripts/rc_smoke.sh
```

Chi tiết: `docs/UPGRADE.md`.

---

## Quick Start (Production - Docker)

```bash
git clone https://github.com/yourusername/vn-bond-lab.git
cd vn-bond-lab

cp .env.example .env
nano .env

docker compose -f docker-compose.prod.yml up -d --build
curl http://localhost:8000/healthz
```

---

## Demo mode

```bash
# Seed demo data (180 ngày)
docker compose run --rm app python -m app.ops seed-demo --days 180

# Bật demo mode
echo "DEMO_MODE=true" >> .env
docker compose restart

open http://localhost:8000
```

