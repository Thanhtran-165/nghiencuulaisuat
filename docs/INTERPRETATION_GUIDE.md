# Interpretation Guide (for non-programmers)

Mục tiêu: biến các chỉ số “học thuật” thành câu trả lời dễ hiểu:
- Thị trường đang ở trạng thái nào?
- Vì sao lại như vậy?
- Cần theo dõi gì tiếp theo?

## 1) Quy tắc đọc nhanh (30 giây)

1) **Nhìn “Ngày dữ liệu” / “Ngày áp dụng” trước**
- Yield curve / HNX: ngày dữ liệu là ngày giao dịch/niêm yết.
- Interbank SBV: “Ngày áp dụng” có thể đứng yên vài ngày; hệ thống vẫn crawl và có “Cập nhật: …”.

2) **Đọc score theo bucket**
- Transmission/VMCI bucket (B0..B4): càng cao càng “thắt chặt / stress”.
- Stress bucket (S0..S4): càng cao càng “stress”.

3) **Xem drivers / alerts**
- Driver lớn nhất (theo trị tuyệt đối) thường giải thích phần lớn biến động.
- Alert có nghĩa “ngưỡng đã bị vượt” (kèm evidence).

## 2) Dashboard: bạn nên hiểu gì?

### Yield (HNX)
Hiển thị 2Y/5Y/10Y và spread 10Y–2Y.
- Spread tăng: thường là “steepening” (kỳ hạn dài tăng nhanh hơn kỳ hạn ngắn).
- Spread giảm: “flattening”.

### Interbank (SBV)
Hiển thị O/N và so sánh kỳ trước.
- Nếu “Ngày áp dụng” không đổi nhưng “Cập nhật” vẫn mới: SBV chưa công bố ngày áp dụng mới.

### Lãi suất ngân hàng (TB)
Là trung bình từ `bank_rates` (snapshot theo `observed_day`).
- Khi ngày không đổi: thường là nguồn crawl chưa có thông tin mới, hoặc job ingest chưa chạy.

### Stress
Chỉ số 0–100 + bucket S0..S4.
- Nếu Stress tăng đột ngột: mở “Vì sao Stress tăng/giảm?” để xem drivers.

## 3) “Nhận định 3 thời hạn” (Insights)

Khái niệm chính:
- Hệ thống dùng “phiên” (observations) thay vì ngày lịch để tránh thiếu dữ liệu.
- Nếu dữ liệu chưa đủ dài, hệ thống có thể “fallback” sang horizon ngắn hơn và sẽ ghi rõ status.

Bạn nên đọc theo cấu trúc:
1) Kết luận 1 câu (conclusion)
2) Xu hướng (trend) + tín hiệu sớm (early signal)
3) Evidence: series nào được dùng + số cặp quan sát hợp lệ (valid_pairs)

## 4) Alerts: cách hiểu đúng

Alert = một điều kiện vượt ngưỡng (threshold) đã kích hoạt.
Bạn nên nhìn:
- `severity` (mức độ)
- `message` (mô tả)
- `metric_value` và `threshold` (bằng chứng số liệu)

## 5) Giới hạn (để tránh hiểu nhầm)

- Dữ liệu VN có thể không có đủ mọi ngày; nhiều phân tích dựa trên “phiên”.
- Một số chỉ số có “cold-start”: khi lịch sử chưa đủ, hệ thống trả điểm trung tính để UI không rỗng và kèm ghi chú hiệu chỉnh.
- Đây là công cụ nghiên cứu/giáo dục, không phải tư vấn đầu tư.

