# Memo: Các phần đang “chờ fill theo ngày” (không backfill được)

Mục tiêu memo:
- Ghi lại rõ **dataset nào không backfill được** (do giới hạn nguồn) nên phải tích luỹ dần theo ngày.
- Nêu **ảnh hưởng học thuật** (calibration/robustness) và **việc cần làm sau khi đủ dữ liệu**.

## 1) Không backfill được (official “latest only”)

### 1.1 Interbank SBV (`interbank_rates`)
- **Nguồn**: SBV portal (official)
- **Tình trạng**: public UI chỉ trả “latest”, không có range params → **tích luỹ snapshot theo ngày**.
- **Hệ quả**:
  - Các metric/alert liên quan O/N và tenor coverage có thể **thiếu history** trong giai đoạn đầu.
  - `date` là “Ngày áp dụng” có thể **trễ/không đổi** dù `fetched_at` vừa cập nhật (dễ bị hiểu nhầm “không load data mới”).
- **Sau khi đủ dữ liệu** (gợi ý tối thiểu):
  - Chuẩn hoá “trading-day baseline” cho các so sánh.
  - Kiểm định ổn định z-score window (20d/60d) theo regime.

### 1.2 Policy SBV (`policy_rates`)
- **Nguồn**: SBV (official)
- **Tình trạng**: chủ yếu là “current / announcement”, discovery có thể thất bại → thường **không backfill lịch sử**.
- **Hệ quả**:
  - `policy_change_flag` có thể hoạt động tốt (event-based) nhưng khó làm nghiên cứu dài hạn.
- **Sau khi đủ dữ liệu**:
  - Xây policy series chuẩn (anchor) theo thông báo, có “effective date” rõ ràng.

## 2) Fallback/Validation cũng “latest only”

### 2.1 ABO Market Watch (`ABO`)
- **Nguồn**: asianbondsonline (non-official)
- **Tình trạng**: chỉ latest → **không giải quyết được backfill lịch sử** cho interbank/yield.
- **Hệ quả**:
  - Dùng để đối chiếu/backup ngắn hạn, không dùng để “lấp lịch sử”.

## 3) Backfill được nhưng bị giới hạn bởi nguồn/endpoint

### 3.1 Secondary trading (`gov_secondary_trading`)
- **Nguồn**: HNX trading endpoint
- **Tình trạng**: catalog hiện cho thấy earliest ~`2025-01-15` → phần trước đó **không có** (hoặc endpoint không phục vụ).
- **Hệ quả**:
  - Alert/driver về turnover có thể **chưa đủ history** để z-score ổn định.
- **Sau khi đủ dữ liệu**:
  - Recalibrate cửa sổ z-score (60d) và kiểm định sensitivity.

## 4) Những nâng cấp học thuật nên “đợi đủ history” để làm chuẩn

- Empirical calibration cho weights (stress/transmission) và threshold alerts theo regime.
- Backtest “bucket mapping” và độ ổn định (stability) theo thời gian.
- Robust outlier handling (MAD/IQR) dựa trên phân phối empirical đủ dài.

