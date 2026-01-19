# Synthesis: Review độc lập (AI #2) vs hiện trạng code

Mục tiêu:
- Đối chiếu các nhận xét “học thuật” và “diễn giải” từ review độc lập với hành vi thực tế trong repo hiện tại.
- Phân loại: **Đồng ý / Một phần / Chưa đúng (do đã thay đổi hoặc hiểu nhầm ngữ cảnh)**.
- Đưa ra action items có thể kiểm chứng (tests + UI/UX).

Tham chiếu nền:
- `docs/ACADEMIC_REVIEW.md`
- `docs/INTERPRETATION_GUIDE.md`
- `docs/METRICS_MAP.md`

## 1) Kết luận nhanh

**Các điểm AI #2 đúng và đáng ưu tiên:**
- **Giả định phân phối chuẩn khi đổi z-score → percentile** (hiện dùng `erf`) cần được ghi rõ và/hoặc thay bằng empirical percentile.
- **Weights & transforms mang tính heuristic** (hard-coded weights, `2.0 - btc`, `-zscore` turnover) cần minh bạch hoá + có cơ chế calibration/ablation tối thiểu.
- **Alerts cần “evidence” định lượng** (metric, threshold, window n) để người dùng hiểu vì sao có cảnh báo.

**Các điểm AI #2 chưa đúng / đã được xử lý theo cách khác:**
- “So với hôm qua” không so theo calendar day; đang lấy **ngày có dữ liệu gần nhất trong DB** (tránh weekend gap):
  - `app/analytics/baseline.py`
- “Temporal leakage do z-score dùng full history”: các truy vấn history trong stress components đều bị chặn bởi `end_date = target_date`:
  - `app/analytics/stress_model.py`
  - Lưu ý: vẫn nên có **test no-leakage** để khóa hành vi.

## 2) Đối chiếu theo từng nhận xét (AI #2)

### 2.1 Temporal leakage trong z-score computation
- **Trạng thái**: _Một phần (cần test), nhưng claim “dùng future data” không đúng trong code hiện tại._
- **Hiện trạng**:
  - Liquidity history: `get_interbank_rates(start=target-60, end=target)` rồi z-score trên danh sách đó.
  - Curve/Auction history: `get_transmission_metrics(start=target-252, end=target)`.
  - Global comparators: `get_global_rates(end=target)` và `gov_yield_curve WHERE date <= target`.
  - File: `app/analytics/stress_model.py`
- **Rủi ro còn lại**:
  - Z-score đang dùng “cửa sổ gồm cả ngày target” (không phải leakage, nhưng có thể muốn exclude-current nếu strict).
- **Action**:
  - Thêm test “history query không bao giờ vượt `target_date`”.
  - (Tuỳ chọn) cân nhắc exclude-current để z-score thuần “past-only”.

### 2.2 Missing data fallback không nhất quán
- **Trạng thái**: _Đồng ý một phần._
- **Hiện trạng**:
  - DQ rules có mức severity khác nhau theo dataset (YC gap vs IB fallback).
  - Ví dụ: interbank tenor coverage có fallback latest `<= target_date` với `WARN`.
  - File: `app/quality/rules.py`
- **Action**:
  - Chuẩn hoá policy theo 3 chế độ: `strict | lenient | warn-only` (có thể qua config).
  - UI cần hiển thị “đang dùng latest available date = X” khi fallback xảy ra.

### 2.3 Percentile approximation từ z-score (erf) giả định normality
- **Trạng thái**: _Đồng ý._
- **Hiện trạng**:
  - Stress model đổi z-score → percentile bằng `erf`.
  - File: `app/analytics/stress_model.py`
- **Action**:
  - Ngắn hạn: ghi rõ “percentile xấp xỉ theo chuẩn” trong UI/docs.
  - Dài hạn: chuyển sang **empirical percentile** (rank trong historical window) + test ổn định.

### 2.4 Weight assignment hard-coded, thiếu validation
- **Trạng thái**: _Đồng ý._
- **Hiện trạng**:
  - `WEIGHTS` cố định trong `BondYStressModel`.
  - File: `app/analytics/stress_model.py`
- **Action**:
  - Tối thiểu: show weights trong UI + giải thích ý nghĩa.
  - Nâng cấp: cho phép override qua config/DB (kèm guardrails tổng weight = 1).

### 2.5 Global comparators không align calendar/timezone
- **Trạng thái**: _Đồng ý một phần._
- **Hiện trạng**:
  - So sánh theo cùng `date` là đơn giản hoá; có thể lệch do lịch giao dịch.
  - File: `app/analytics/stress_model.py`
- **Action**:
  - Ngắn hạn: thêm disclaimer “so sánh theo calendar date”.
  - Dài hạn: align theo trading calendar hoặc dùng lag (t+1) cho series US.

### 2.6 Winsorize ±3 z-score
- **Trạng thái**: _Đồng ý (trade-off)._
- **Hiện trạng**:
  - Có winsorize để tránh outlier phá scale.
  - File: `app/analytics/stress_model.py`
- **Action**:
  - Document rationale + (tuỳ chọn) cấu hình ngưỡng winsor.

### 2.7 Auction stress heuristic `2.0 - bid_to_cover`
- **Trạng thái**: _Đồng ý._
- **Hiện trạng**:
  - Heuristic để đảo chiều (BTC thấp → stress cao).
  - File: `app/analytics/stress_model.py`
- **Action**:
  - Document rõ “proxy/heuristic”.
  - Nếu muốn “học thuật hơn”: mapping phi tuyến hoặc calibration theo historical distribution.

### 2.8 Turnover stress `-zscore` scaling
- **Trạng thái**: _Đồng ý một phần._
- **Hiện trạng**:
  - Turnover component đang dùng z-score (đã nằm trên scale chuẩn hoá), đảo dấu để cùng chiều stress.
  - File: `app/analytics/stress_model.py`
- **Action**:
  - UI cần giải thích “đảo chiều để cùng hướng”.
  - (Tuỳ chọn) đổi sang percentile giống các component khác để thống nhất.

### 2.9 Stress bucket thresholds cố định
- **Trạng thái**: _Đồng ý (nhưng hợp lý cho v1)._
- **Hiện trạng**:
  - S0..S4 chia theo khoảng điểm.
  - File: `app/analytics/stress_model.py`
- **Action**:
  - Giữ cố định nhưng ghi rõ, hoặc thêm “regime-aware buckets” về sau.

## 3) Diễn giải (Interpretability) — đối chiếu

### 3.1 “Ngày áp dụng” vs “Cập nhật”
- **Trạng thái**: _Đã có hiển thị trong UI, nhưng cần tooltip giải thích._
- **Hiện trạng**:
  - Interbank pages hiển thị cả `Ngày áp dụng` và `Cập nhật`.
  - Files: `frontend/src/app/interbank/InterbankClient.tsx`, `frontend/src/app/page.tsx`
- **Action**:
  - Thêm tooltip ngắn: “SBV công bố ‘ngày áp dụng’ có thể không đổi dù dữ liệu vừa được crawl lại.”

### 3.2 “So với hôm qua” baseline day
- **Trạng thái**: _Đa số đã đúng theo DB-available date._
- **Hiện trạng**:
  - Baseline tìm `MAX(date) < target_date` trong DB thay vì trừ 1 ngày lịch.
  - File: `app/analytics/baseline.py`
- **Action**:
  - UI hiển thị rõ “so với ngày X” (đã có ở Interbank; cân nhắc mở rộng các card khác).

### 3.3 Alert messages thiếu evidence
- **Trạng thái**: _Cần nâng cấp (ưu tiên)._
- **Action**:
  - Chuẩn hoá schema alert: luôn có `metric`, `value`, `threshold`, `window`, `note` và UI hiển thị.

## 4) Roadmap (ưu tiên triển khai)

P0 (trong 1–2 phiên làm):
- UI tooltips: applied_date vs fetched_at.
- Hiển thị weights trong Stress drivers.
- Alert evidence: bổ sung `source_data.evidence` và UI render.
- Dashboard freshness: hiển thị “trễ N ngày” khi nguồn chưa có data mới.

P1 (khi muốn “học thuật hơn”):
- Empirical percentile (thay `erf`).
- Configurable weights + sensitivity tests.
- Calendar alignment/disclaimer cho global comparators.
