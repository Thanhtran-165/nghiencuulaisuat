# Audit (Technical Debt & Cleanup)

Mục tiêu: loại bỏ logic thừa/lặp, giảm drift giữa các luồng (CLI / scripts / API / UI), và làm dự án dễ vận hành như một sản phẩm.

## Trạng thái hiện tại (tóm tắt)

- Backend FastAPI là “engine” (DB/ingest/API). UI chính là Next.js (frontend).
- Tự động ingest hiện đang dựa vào OS scheduler (macOS LaunchAgent) nhiều hơn là scheduler nội bộ của backend.
- Một số dataset (ví dụ Interbank SBV) có “ngày áp dụng” có thể lag so với ngày crawl; UI đã hiển thị thêm “Cập nhật: …” để giảm hiểu nhầm.

## Các điểm rủi ro / lặp / dễ drift

1) **Drift danh sách providers chạy “daily”**
- `python -m app.ingest daily` mặc định trước đây chạy toàn bộ providers (kể cả `abo`).
- Scripts/LaunchAgents có thể cấu hình khác → dễ hiểu nhầm “tại sao dataset A không cập nhật”.
- Đã khắc phục: gom default daily providers vào `IngestionPipeline.DEFAULT_DAILY_PROVIDERS` và dùng chung trong `/api/admin/ingest/daily`.

2) **Hai cơ chế scheduler song song**
- `app/main.py` có in-process APScheduler (bật bằng `SCHEDULER_ENABLED=true`).
- Ngoài ra có `app/scheduler.py` (TaskScheduler) nhưng không được dùng trong runtime.
- Đã khắc phục: đánh dấu `app/scheduler.py` là DEPRECATED để tránh nhầm.
- Khuyến nghị: chọn 1 trong 2 hướng vận hành:
  - (A) OS scheduler (LaunchAgent/systemd) + endpoint `/api/admin/ingest/daily`, hoặc
  - (B) bật `SCHEDULER_ENABLED=true` và vận hành ingest trong process.

3) **Legacy UI templates vs Next.js UI**
- Có các file `app/templates/*.html` gọi `/api/bank-rates/*` (legacy).
- Hiện backend default redirect HTML sang Next.js (legacy UI tắt).
- Khuyến nghị: nếu không dùng legacy UI nữa, lên kế hoạch xoá templates + routes legacy, hoặc tách sang folder `legacy/` và ghi rõ trạng thái.

## Các việc nên làm tiếp (đề xuất thứ tự)

1) **Chuẩn hoá vận hành ingest**
- Mặc định: dùng LaunchAgent gọi `/api/admin/ingest/daily` (giảm rủi ro DuckDB file lock).
- Ensure LaunchAgent ingest providers bao gồm `lai_suat_rates`.

2) **Chuẩn hoá API surface**
- Quy ước rõ các endpoint “canonical” và các endpoint “alias/deprecated”.
- Dọn các route cũ nếu không còn UI nào dùng.

3) **Audit UI fetch patterns**
- Ưu tiên fetch qua `/api/...` (Next rewrite) thay vì hardcode `BACKEND_URL` từng page.
- Đảm bảo cache policy thống nhất (đa số `no-store` cho dashboard).

4) **Kiểm tra test/smoke**
- Hiện có một số test smoke 404 (cần xác định do redirect/route policy hay do thiếu page).
- Đưa về một bộ smoke test “đủ dùng” cho release.

