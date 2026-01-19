"use client";

import { useState, useMemo, useEffect } from "react";
import { TopTabs } from "@/components/TopTabs";
import { GlassCard } from "@/components/GlassCard";
import { HistoryChart } from "@/components/HistoryChart";
import { ChartSkeleton } from "@/components/Skeleton";
import { useSeries, useLatestRates, useRatesHistory, useMetaLatest } from "@/lib/hooks";
import { formatDate, formatRate } from "@/lib/utils";

export default function LichSuPage() {
  const [productType, setProductType] = useState<"deposit" | "loan">("deposit");
  const [selectedBank, setSelectedBank] = useState<string>("");
  const [selectedSeries, setSelectedSeries] = useState<string>("");
  const [selectedTerm, setSelectedTerm] = useState<number | null>(12);

  // React Query hooks
  const { data: meta } = useMetaLatest();
  const { data: series = [] } = useSeries();

  // Latest rates query (for bank list)
  const {
    data: latestData,
    isLoading: isLoadingBanks,
    error: banksError
  } = useLatestRates(selectedSeries, selectedTerm || undefined);

  // History query
  const {
    data: historyData,
    isLoading: isLoadingHistory,
    error: historyError,
    refetch
  } = useRatesHistory(selectedBank, selectedSeries, selectedTerm || undefined, 30);

  // Filter series based on product type
  const filteredSeries = useMemo(() =>
    series.filter(s =>
      productType === "deposit"
        ? s.code.startsWith("deposit_")
        : s.code.startsWith("loan_")
    ),
  [series, productType]
  );

  // Get banks list from latest data
  const banks = latestData?.rows || [];

  // Auto-select first bank when banks load
  useEffect(() => {
    if (banks.length > 0 && !selectedBank) {
      setSelectedBank(banks[0].bank_name);
    }
  }, [banks, selectedBank]);

  // Auto-select first series when filtered series change
  useEffect(() => {
    if (!selectedSeries && filteredSeries.length > 0) {
      setSelectedSeries(filteredSeries[0].code);
    }
  }, [filteredSeries, selectedSeries]);

  const seriesLabel = series.find(s => s.code === selectedSeries)?.description || selectedSeries;
  const error = banksError || historyError;

  // Check if data is old (>24h)
  const isDataOld = meta?.latest_scraped_at
    ? Date.now() - new Date(meta.latest_scraped_at).getTime() > 24 * 60 * 60 * 1000
    : false;

  return (
    <div>
      <TopTabs basePath="/lai-suat" />

      {/* Header with metadata */}
      <div className="mb-6">
        <div className="flex items-start justify-between mb-2">
          <div>
            <h1 className="text-3xl font-bold text-white mb-2">Lịch sử lãi suất</h1>
            <p className="text-sm text-white/60">
              Xem biểu đồ lịch sử lãi suất của các ngân hàng
            </p>
          </div>

          {/* Refetch button */}
          <button
            onClick={() => refetch()}
            disabled={isLoadingHistory}
            className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50 flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Tải lại
          </button>
        </div>

        {/* Last updated + old data warning */}
        {meta?.latest_scraped_at && (
          <div className="flex items-center gap-3 text-sm">
            <span className="text-white/40">
              Cập nhật lần cuối: {formatDate(meta.latest_scraped_at)}
            </span>
            {isDataOld && (
              <span className="px-2 py-1 bg-yellow-500/20 text-yellow-300 rounded text-xs">
                Dữ liệu có thể đã cũ
              </span>
            )}
          </div>
        )}
      </div>

      {/* Controls */}
      <GlassCard className="mb-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Product Type */}
          <div>
            <label className="block text-sm text-white/60 mb-2">Loại lãi suất</label>
            <select
              value={productType}
              onChange={(e) => {
                setProductType(e.target.value as "deposit" | "loan");
                setSelectedBank("");
                setSelectedTerm(12);
              }}
              className="glass-input w-full px-4 py-2 rounded-lg text-white text-sm"
            >
              <option value="deposit">Tiền gửi</option>
              <option value="loan">Khoản vay</option>
            </select>
          </div>

          {/* Series */}
          <div>
            <label className="block text-sm text-white/60 mb-2">Loại sản phẩm</label>
            <select
              value={selectedSeries}
              onChange={(e) => setSelectedSeries(e.target.value)}
              disabled={!selectedSeries}
              className="glass-input w-full px-4 py-2 rounded-lg text-white text-sm disabled:opacity-50"
            >
              {filteredSeries.map(s => (
                <option key={s.code} value={s.code}>
                  {s.description || s.code}
                </option>
              ))}
            </select>
          </div>

          {/* Term (for deposits) */}
          {productType === "deposit" && (
            <div>
              <label className="block text-sm text-white/60 mb-2">Kỳ hạn</label>
              <select
                value={selectedTerm || ""}
                onChange={(e) => setSelectedTerm(Number(e.target.value))}
                className="glass-input w-full px-4 py-2 rounded-lg text-white text-sm"
              >
                <option value={1}>1 tháng</option>
                <option value={3}>3 tháng</option>
                <option value={6}>6 tháng</option>
                <option value={12}>12 tháng</option>
                <option value={18}>18 tháng</option>
                <option value={24}>24 tháng</option>
                <option value={36}>36 tháng</option>
              </select>
            </div>
          )}

          {/* Bank */}
          <div>
            <label className="block text-sm text-white/60 mb-2">Ngân hàng</label>
            <select
              value={selectedBank}
              onChange={(e) => setSelectedBank(e.target.value)}
              disabled={banks.length === 0}
              className="glass-input w-full px-4 py-2 rounded-lg text-white text-sm disabled:opacity-50"
            >
              <option value="">Chọn ngân hàng...</option>
              {banks.map((bank: any) => (
                <option key={bank.bank_name} value={bank.bank_name}>
                  {bank.bank_name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </GlassCard>

      {/* Error State */}
      {error && (
        <GlassCard className="mb-6">
          <p className="text-red-400 text-lg mb-2">Lỗi</p>
          <p className="text-white/60 mb-4">{error.message}</p>
          <button
            onClick={() => refetch()}
            className="glass-button px-4 py-2 rounded-lg text-white text-sm"
          >
            Thử lại
          </button>
        </GlassCard>
      )}

      {/* Chart Container with fixed height to prevent layout shift */}
      <div className="min-h-[420px]">
        {isLoadingHistory && !historyData ? (
          <ChartSkeleton height={400} />
        ) : !historyData || historyData.points.length === 0 ? (
          /* Empty state: No data available */
          <GlassCard>
            <div className="flex flex-col items-center justify-center h-[420px] text-center px-8">
              <svg className="w-16 h-16 text-white/20 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              <h3 className="text-xl font-semibold text-white mb-2">Chưa có dữ liệu lịch sử</h3>
              <p className="text-white/60 mb-2">
                Dữ liệu mới được thu thập từ {meta?.latest_scraped_at ? formatDate(meta.latest_scraped_at) : "chưa xác định"}.
              </p>
              <p className="text-white/40 text-sm mb-4">
                Lịch sử sẽ được hiển thị sau vài ngày thu thập dữ liệu.
              </p>
              <button
                onClick={() => refetch()}
                className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10"
              >
                Tải lại
              </button>
            </div>
          </GlassCard>
        ) : historyData.points.length === 1 ? (
          /* Single point state: Data is being accumulated */
          <GlassCard>
            <div className="flex flex-col items-center justify-center h-[420px] text-center px-8">
              <div className="w-16 h-16 bg-yellow-500/20 rounded-full flex items-center justify-center mb-4">
                <svg className="w-8 h-8 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">Dữ liệu lịch sử đang được tích lũy</h3>
              <p className="text-white/60 mb-4">
                Hiện tại mới có <span className="text-yellow-300 font-semibold">1 bản ghi</span> vào ngày{" "}
                <span className="text-yellow-300 font-semibold">
                  {historyData.points[0].scraped_at ? formatDate(historyData.points[0].scraped_at) : "chưa xác định"}
                </span>.
              </p>
              <p className="text-white/40 text-sm mb-6">
                Cần scrape thêm ngày để vẽ xu hướng lãi suất.
              </p>

              {/* Single data point display */}
              <div className="bg-white/5 rounded-lg p-4 mb-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-white/40 mb-1">Ngân hàng</p>
                    <p className="text-white font-medium">{historyData.meta.bank_name}</p>
                  </div>
                  <div>
                    <p className="text-white/40 mb-1">Loại sản phẩm</p>
                    <p className="text-white font-medium">{seriesLabel}</p>
                  </div>
                  <div>
                    <p className="text-white/40 mb-1">Lãi suất</p>
                    <p className="text-2xl font-bold text-emerald-400">
                      {historyData.points[0].rate_pct !== null ? formatRate(historyData.points[0].rate_pct) : "N/A"}
                    </p>
                  </div>
                  <div>
                    <p className="text-white/40 mb-1">Kỳ hạn</p>
                    <p className="text-white font-medium">
                      {selectedTerm ? `${selectedTerm} tháng` : "Không áp dụng"}
                    </p>
                  </div>
                </div>
              </div>

              <button
                onClick={() => refetch()}
                className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10"
              >
                Tải lại
              </button>
            </div>
          </GlassCard>
        ) : (
          /* Normal state: 2+ points - render chart */
          <HistoryChart
            data={historyData.points}
            title={`Lịch sử ${seriesLabel} - ${selectedBank}${selectedTerm ? ` (${selectedTerm} tháng)` : ""}`}
            type={productType}
          />
        )}
      </div>
    </div>
  );
}
