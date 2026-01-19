# Metrics Map (Data Lineage)

Mục tiêu: trả lời nhanh 5 câu hỏi cho mỗi chỉ số:
1) Nguồn dữ liệu ở đâu?
2) Lưu vào bảng nào trong DuckDB?
3) Tính toán ở module nào?
4) Expose qua API endpoint nào?
5) Hiển thị ở UI trang nào?

## A) Nguồn dữ liệu → bảng DuckDB

| Khối | Provider | Bảng DuckDB | Ghi chú ngày (date semantics) |
|---|---|---|---|
| Yield curve (HNX) | `hnx_yield_curve` | `gov_yield_curve` | Date = ngày dữ liệu theo HNX; không phải mọi ngày đều có dữ liệu |
| Yield change stats (HNX FTP PDF) | `hnx_ftp_pdf` | `gov_yield_change_stats` | Phục vụ phân tích thống kê/QA |
| Auction (HNX) | `hnx_auction` | `gov_auction_results` | Date = ngày phiên đấu thầu |
| Secondary trading (HNX) | `hnx_trading` | `gov_secondary_trading` | Date = ngày giao dịch |
| Interbank (SBV) | `sbv_interbank` | `interbank_rates` | Date = “Ngày áp dụng” (có thể lag so với ngày crawl); có `fetched_at` |
| Policy rates (SBV) | `sbv_policy` | `policy_rates` | Date = ngày công bố/hiệu lực theo SBV |
| Bank rates (Lãi suất NH) | `lai_suat_rates` | `bank_rates` | Date = `observed_day` (snapshot theo ngày quan sát) |
| Global rates (FRED) | `fred_global` | `global_rates_daily` | Optional; cần `FRED_API_KEY` |

## B) Analytics → bảng kết quả

| Khối | Module compute | Bảng kết quả | Ghi chú |
|---|---|---|---|
| Transmission metrics + alerts | `app/analytics/transmission.py` | `transmission_daily_metrics`, `transmission_alerts` | Metrics dạng `{value/value_text, sources}` để giải thích nguồn |
| Daily snapshot (VN) | `app/analytics/snapshot.py` | `daily_snapshots` | Snapshot đọc metrics đã persist trong `transmission_daily_metrics` |
| BondY Stress | `app/analytics/stress_model.py` | `bondy_stress_daily` | Phụ thuộc `transmission_score` + các series nền |
| “Nhận định 3 thời hạn” | `app/analytics/horizon_assessment.py` | (không persist; trả JSON) | Dùng “phiên” (observations) thay vì calendar days |

## C) API endpoints chính

| Use case | Endpoint | Nguồn dữ liệu |
|---|---|---|
| Dashboard summary | `GET /api/dashboard/metrics` | Aggregations từ DuckDB (yield/interbank/bank_rates/stress) |
| Insights (3 thời hạn) | `GET /api/insights/horizons` | `HorizonAssessmentEngine.build_payload()` |
| Interbank latest/compare | `GET /api/interbank/latest`, `GET /api/interbank/compare` | `interbank_rates` (ưu tiên SBV, có `fetched_at`) |
| Stress latest/series | `GET /api/stress/latest`, `GET /api/stress/timeseries` | `bondy_stress_daily` |
| Snapshot JSON | `GET /api/snapshot/today` | `DailySnapshotGenerator.generate_snapshot()` |
| Manual ingest | `POST /api/admin/ingest/daily` | `IngestionPipeline.run_daily()` |

## D) UI pages (Next.js)

| Trang | Path | Data gọi |
|---|---|---|
| Dashboard | `frontend/src/app/page.tsx` | `/api/dashboard/metrics`, `/api/interbank/compare`, `/api/insights/horizons` |
| Interbank | `frontend/src/app/interbank/page.tsx` | `/api/interbank/*` |
| Stress | `frontend/src/app/stress/page.tsx` | `/api/stress/*` + compute button `/api/admin/stress/compute` |
| Lãi suất NH | `frontend/src/app/lai-suat/*` | `/api/lai-suat/*` (từ `bank_rates`) |

