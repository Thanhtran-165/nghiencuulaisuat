"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api, LatestRateItem } from "@/lib/api";
import { formatDate } from "@/lib/utils";

// Series labels in Vietnamese
const SERIES_LABELS: Record<string, string> = {
  deposit_online: "Tiền gửi Online",
  deposit_tai_quay: "Tiền gửi Tại quầy",
  loan_the_chap: "Vay Thế chấp",
  loan_tin_chap: "Vay Tín chấp",
};

// Series available for each context
const SERIES_BY_CONTEXT: Record<"loan" | "deposit", string[]> = {
  loan: ["loan_the_chap", "loan_tin_chap"],
  deposit: ["deposit_online", "deposit_tai_quay"],
};

// Term options for deposits
const TERM_OPTIONS = [
  { value: 1, label: "1 tháng" },
  { value: 3, label: "3 tháng" },
  { value: 6, label: "6 tháng" },
  { value: 12, label: "12 tháng" },
  { value: 18, label: "18 tháng" },
  { value: 24, label: "24 tháng" },
  { value: 36, label: "36 tháng" },
];

export interface RateMetadata {
  bankName: string;
  seriesCode: string;
  seriesLabel: string;
  scrapedAt: string;
  sourceUrl: string;
  isRange?: boolean;
  isMin?: boolean;
}

interface RateSourceSelectorProps {
  context: "loan" | "deposit";
  onRateChange: (rate: number | null, metadata: RateMetadata | null) => void;
}

export function RateSourceSelector({ context, onRateChange }: RateSourceSelectorProps) {
  const [mode, setMode] = useState<"bank" | "manual">("bank");
  const [banks, setBanks] = useState<string[]>([]);
  const [selectedBank, setSelectedBank] = useState<string>("");
  const [selectedSeries, setSelectedSeries] = useState<string>("");
  const [selectedTerm, setSelectedTerm] = useState<number>(12);
  const [rateItem, setRateItem] = useState<LatestRateItem | null>(null);
  const [loadingBanks, setLoadingBanks] = useState(false);
  const [loadingRate, setLoadingRate] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Use ref to store latest onRateChange to avoid dependency issues
  const onRateChangeRef = useRef(onRateChange);
  onRateChangeRef.current = onRateChange;

  // Fetch banks on mount
  useEffect(() => {
    const fetchBanks = async () => {
      setLoadingBanks(true);
      setError(null);
      try {
        const data = await api.banks();
        setBanks(data);
      } catch (err: any) {
        setError(err.message || "Không thể tải danh sách ngân hàng");
      } finally {
        setLoadingBanks(false);
      }
    };

    if (mode === "bank") {
      fetchBanks();
    }
  }, [mode]);

  // Fetch rate when bank, series, or term changes
  useEffect(() => {
    const abortController = new AbortController();

    const fetchRate = async () => {
      if (!selectedBank || !selectedSeries) {
        setRateItem(null);
        onRateChangeRef.current(null, null);
        return;
      }

      setLoadingRate(true);
      setError(null);

      try {
        let data;
        if (context === "deposit") {
          // Deposit requires term_months
          data = await api.latest({
            series_code: selectedSeries,
            term_months: selectedTerm,
          });
        } else {
          // Loan doesn't use term
          data = await api.latest({
            series_code: selectedSeries,
          });
        }

        // Check if request was aborted
        if (abortController.signal.aborted) {
          return;
        }

        // Find the rate for the selected bank
        const item = data.rows.find((row) => row.bank_name === selectedBank);

        if (!item) {
          setError("Không có dữ liệu lãi suất phù hợp cho lựa chọn này. Vui lòng đổi lựa chọn hoặc nhập thủ công.");
          setRateItem(null);
          onRateChangeRef.current(null, null);
          return;
        }

        setRateItem(item);

        // Determine the rate to use
        let rate: number | null = null;
        let metadata: RateMetadata | null = null;

        if (context === "loan") {
          // For loans, prioritize rate_min_pct, then rate_pct
          if (item.rate_min_pct !== null && item.rate_min_pct !== undefined) {
            rate = item.rate_min_pct;
            metadata = {
              bankName: item.bank_name,
              seriesCode: item.series_code,
              seriesLabel: SERIES_LABELS[item.series_code] || item.series_code,
              scrapedAt: item.scraped_at,
              sourceUrl: item.source_url,
              isRange: item.rate_max_pct !== null && item.rate_max_pct !== undefined,
              isMin: true,
            };
          } else if (item.rate_pct !== null && item.rate_pct !== undefined) {
            rate = item.rate_pct;
            metadata = {
              bankName: item.bank_name,
              seriesCode: item.series_code,
              seriesLabel: SERIES_LABELS[item.series_code] || item.series_code,
              scrapedAt: item.scraped_at,
              sourceUrl: item.source_url,
            };
          }
        } else {
          // For deposits, use rate_pct
          if (item.rate_pct !== null && item.rate_pct !== undefined) {
            rate = item.rate_pct;
            metadata = {
              bankName: item.bank_name,
              seriesCode: item.series_code,
              seriesLabel: SERIES_LABELS[item.series_code] || item.series_code,
              scrapedAt: item.scraped_at,
              sourceUrl: item.source_url,
            };
          }
        }

        // Check if request was aborted before calling callback
        if (abortController.signal.aborted) {
          return;
        }

        onRateChangeRef.current(rate, metadata);

      } catch (err: any) {
        // Ignore errors from aborted requests
        if (abortController.signal.aborted) {
          return;
        }
        setError(err.message || "Không thể tải dữ liệu lãi suất");
        setRateItem(null);
        onRateChangeRef.current(null, null);
      } finally {
        if (!abortController.signal.aborted) {
          setLoadingRate(false);
        }
      }
    };

    if (mode === "bank" && selectedBank && selectedSeries) {
      fetchRate();
    } else {
      setRateItem(null);
      onRateChangeRef.current(null, null);
    }

    // Cleanup function to abort request on unmount or dependency change
    return () => {
      abortController.abort();
    };
  }, [mode, selectedBank, selectedSeries, selectedTerm, context]); // Removed onRateChange from deps

  // Reset selections when switching modes
  const handleModeChange = (newMode: "bank" | "manual") => {
    setMode(newMode);
    if (newMode === "manual") {
      setSelectedBank("");
      setSelectedSeries("");
      setSelectedTerm(12);
      setRateItem(null);
      setError(null);
      onRateChangeRef.current(null, null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Mode Selector */}
      <div>
        <label className="block text-sm text-white/70 mb-2">
          Nguồn lãi suất
        </label>
        <div className="flex gap-2">
          <button
            onClick={() => handleModeChange("bank")}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              mode === "bank"
                ? "bg-blue-500 text-white"
                : "bg-white/5 text-white/60 hover:bg-white/10"
            }`}
          >
            Từ ngân hàng
          </button>
          <button
            onClick={() => handleModeChange("manual")}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              mode === "manual"
                ? "bg-blue-500 text-white"
                : "bg-white/5 text-white/60 hover:bg-white/10"
            }`}
          >
            Nhập thủ công
          </button>
        </div>
      </div>

      {/* Bank Mode */}
      {mode === "bank" && (
        <div className="space-y-3">
          {/* Bank Dropdown */}
          <div>
            <label className="block text-sm text-white/70 mb-1">
              Ngân hàng <span className="text-red-400">*</span>
            </label>
            {loadingBanks ? (
              <div className="w-full px-4 py-2 rounded-lg glass-input text-white/60">
                Đang tải...
              </div>
            ) : (
              <select
                value={selectedBank}
                onChange={(e) => setSelectedBank(e.target.value)}
                className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
              >
                <option value="">Chọn ngân hàng</option>
                {banks.map((bank) => (
                  <option key={bank} value={bank}>
                    {bank}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Series Dropdown */}
          <div>
            <label className="block text-sm text-white/70 mb-1">
              Loại sản phẩm <span className="text-red-400">*</span>
            </label>
            <select
              value={selectedSeries}
              onChange={(e) => setSelectedSeries(e.target.value)}
              disabled={!selectedBank}
              className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20 disabled:opacity-50"
            >
              <option value="">Chọn sản phẩm</option>
              {SERIES_BY_CONTEXT[context].map((seriesCode) => (
                <option key={seriesCode} value={seriesCode}>
                  {SERIES_LABELS[seriesCode] || seriesCode}
                </option>
              ))}
            </select>
          </div>

          {/* Term Dropdown (Deposit Only) */}
          {context === "deposit" && (
            <div>
              <label className="block text-sm text-white/70 mb-1">
                Kỳ hạn <span className="text-red-400">*</span>
              </label>
              <select
                value={selectedTerm}
                onChange={(e) => setSelectedTerm(Number(e.target.value))}
                disabled={!selectedBank || !selectedSeries}
                className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20 disabled:opacity-50"
              >
                {TERM_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Loading State */}
          {loadingRate && (
            <div className="text-sm text-white/60">
              Đang tải dữ liệu lãi suất...
            </div>
          )}

          {/* Rate Metadata */}
          {rateItem && !loadingRate && (
            <div className="text-xs text-white/50 space-y-1">
              <div className="flex items-center gap-2">
                <span>Nguồn:</span>
                <span className="text-white/70">{rateItem.bank_name}</span>
                <span>·</span>
                <span className="text-white/70">
                  {SERIES_LABELS[rateItem.series_code] || rateItem.series_code}
                </span>
                {context === "deposit" && rateItem.term_label && (
                  <>
                    <span>·</span>
                    <span className="text-white/70">{rateItem.term_label}</span>
                  </>
                )}
              </div>
              <div>
                Cập nhật: <span className="text-white/70">{formatDate(rateItem.scraped_at)}</span>
              </div>
              {(rateItem.rate_min_pct !== null && rateItem.rate_min_pct !== undefined) && (
                <div className="flex items-center gap-1">
                  <span className="px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded text-xs font-semibold">
                    Từ
                  </span>
                  {rateItem.rate_max_pct !== null && rateItem.rate_max_pct !== undefined && (
                    <span className="text-white/50">
                      {" "} đến {rateItem.rate_max_pct.toFixed(2)}%
                    </span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="p-3 bg-red-500/20 border border-red-500/30 rounded-lg">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
