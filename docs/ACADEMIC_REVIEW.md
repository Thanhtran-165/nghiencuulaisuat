# Academic Review (v1)

Mục tiêu tài liệu này:
- Đánh giá chất lượng học thuật của các chỉ số “nặng học thuật” trong dự án.
- Chỉ ra rủi ro (leakage, proxy validity, robustness) và đề xuất cải thiện có thể kiểm chứng bằng tests.

Tham chiếu bản đồ dữ liệu: `docs/METRICS_MAP.md`.

## 1) Quy ước & semantics quan trọng

### 1.1 “Phiên” (observations) thay vì calendar days
- Một số phân tích (Insights horizons) dùng “phiên” vì dữ liệu thị trường VN không có đủ mọi ngày.
- Hệ quả: horizon “Δ30 phiên” ≠ “30 ngày lịch”.

### 1.2 “Ngày áp dụng” vs “ngày cập nhật”
- Interbank SBV: `date` là “Ngày áp dụng”; `fetched_at` là lúc crawl.
- Khi nguồn không đổi “Ngày áp dụng”, UI có thể thấy “cập nhật” nhưng `date` không đổi.

## 2) Transmission / VMCI (core học thuật)

**Mục tiêu**: tạo một thước đo tổng hợp 0–100 phản ánh mức “thắt chặt / stress” của điều kiện thị trường.

### 2.1 Định nghĩa thành phần (construct validity)
Module: `app/analytics/transmission.py`
- Curve: level/slope/curvature + z-score
- Liquidity: interbank O/N + spread + z-score
- Supply: auction sold / bid-to-cover / cutoff changes
- Demand: secondary turnover/value + z-score
- Policy: anchor + spread z-score + term premium proxy

Điểm cần review sâu:
- Dấu (+/–) cho từng component có nhất quán với “stress tăng” không.
- Các z-score có cùng cửa sổ và cùng phương pháp chuẩn hoá không.

### 2.2 Leakage & “train-only” calibration
Đã có cơ chế train-only cho bucket/z-score trong lớp VMCI-now:
- `TransmissionAnalytics._compute_vmci_now()` dùng `date < target_date` cho history.

Checklist:
- Các nơi khác (PCA dynamic weights, alert z-score) phải đảm bảo không dùng “today” trong thống kê train.

### 2.3 Cold-start / dữ liệu ít
Hiện tại khi thiếu đủ component z-score, `transmission_score` trả **neutral 50** (B2):
- `TransmissionAnalytics._compute_transmission_score()` fallback `50.0` để tránh UI “trống”.

Trade-off:
- Pro: UI không rỗng, series bắt đầu tích luỹ sớm.
- Con: Có thể tạo “false sense of precision” nếu không gắn nhãn “calibrating”.

Đề xuất học thuật:
- Luôn kèm `sources.note` khi score là neutral fallback.
- UI cần hiển thị “đang hiệu chỉnh (calibrating)” nếu `n_train < min_n`.

## 3) Alerts (threshold-based)

Module: `app/analytics/alert_engine.py`, gọi từ `TransmissionAnalytics.detect_alerts()`.

Điểm mạnh:
- Thresholds có thể cấu hình trong DB (`alert_thresholds`), không hardcode.

Rủi ro:
- Fresh DB có thể không có threshold rows → cần default fallback (đã có).

Checklist học thuật:
- Alert dựa trên z-score/history phải dùng `date < target_date` để tránh leakage.
- Alert message cần kèm evidence (metric_value, threshold, window n).

Hiện trạng:
- `source_data` của alerts có thêm block `evidence` (metric/method/unit/baseline/n/…); UI Transmission hiển thị tóm tắt evidence trong modal “Chi tiết”.

## 4) BondY Stress (composite stress index)

Module: `app/analytics/stress_model.py`

### 4.1 Định nghĩa
- Stress index 0–100 là composite dựa trên percentile ranks của:
  - transmission_score
  - liquidity/curve/auction/turnover stress (z-score/levels)
- Bucket S0..S4 theo khoảng điểm.

### 4.2 Rủi ro học thuật
1) Percentile ranks phụ thuộc “history window” và missingness.
2) Transmission_score là “anchor” nhưng bản thân có cold-start neutral 50.
3) Z-score cửa sổ 60/252 có thể quá ngắn/dài tuỳ regime.

Đề xuất:
- Explicitly log và expose `data_availability` + `drivers` (đã có).
- Thêm test “stress không tính khi transmission_score thiếu” và “stress stable với missing days”.

## 5) Insights: “Nhận định 3 thời hạn”

Module: `app/analytics/horizon_assessment.py`

Điểm học thuật cần kiểm tra:
- Horizon theo “phiên” có phù hợp cho từng loại series (yield vs interbank vs policy)?
- Quy tắc readiness (min_pairs) có hợp lý và có bias khi missingness tăng?
- Nếu fallback sang horizon ngắn hơn, phải hiển thị rõ ràng (status: fallback/limited).

## 6) Đề xuất tests (ưu tiên)

1) **No leakage**: đảm bảo mọi thống kê train dùng `date < target_date`.
2) **Cold-start labeling**: khi fallback neutral score, phải có `sources.note`.
3) **Applied date semantics**: interbank compare trả `today_date` và `today_fetched_at` khác nhau khi SBV không đổi ngày áp dụng.
4) **Missingness robustness**: horizon theo “phiên” không crash khi thiếu ngày.
5) **Alert defaults**: fresh DB vẫn detect được alerts theo default thresholds.
