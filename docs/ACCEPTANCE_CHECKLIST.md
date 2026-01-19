# Acceptance Checklist (Release Readiness)

Mục tiêu: có checklist “pass/fail” để mỗi lần release không phụ thuộc trí nhớ.

## A) Repo hygiene

- [ ] Không commit `.env` / secrets
- [ ] Không commit DB/logs: `*.duckdb`, `data/duckdb/*`, `logs/*`
- [ ] `README.md` có link docs chính, hướng dẫn chạy local + Docker
- [ ] `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md` tồn tại

## B) CI (GitHub Actions)

- [ ] Workflow `CI` chạy xanh trên `main`
- [ ] `docker compose build` thành công
- [ ] `docker compose run --rm app pytest -q` pass

## C) API contracts (smoke)

Chạy backend (Docker hoặc local), rồi kiểm tra:

- [ ] `GET /healthz` trả `{"status":"ok",...}`
- [ ] `GET /readyz` trả `status=ok`
- [ ] `GET /api/dashboard/metrics` trả JSON hợp lệ
- [ ] `GET /api/interbank/compare` có `today_date` + `today_fetched_at` (nếu có dữ liệu)
- [ ] `GET /api/snapshot/today` trả JSON snapshot (không 500)

## D) Data semantics

- [ ] Interbank: UI hiển thị “Ngày áp dụng” và “Cập nhật” (tránh nhầm `date` vs `fetched_at`)
- [ ] Bank rates: `bank_rates.date` lấy từ `observed_day` (snapshot theo ngày quan sát)
- [ ] Transmission score: nếu cold-start, có ghi chú “calibrating/neutral”

## E) Ops / vận hành ingest

- [ ] `POST /api/admin/ingest/daily` chạy không lỗi (hoặc qua UI nút “Cập nhật dữ liệu”)
- [ ] Nếu dùng macOS: LaunchAgent ingest có chạy và log ở `~/Library/Application Support/vn-bond-lab/logs/`

