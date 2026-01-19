"use client";

import { useEffect, useState } from "react";
import { TopTabs } from "@/components/TopTabs";
import { GlassCard } from "@/components/GlassCard";
import { api, LatestRateItem } from "@/lib/api";
import { formatDate, formatRate } from "@/lib/utils";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";

type TabType = "deposit" | "loan";

interface ComparisonData {
  bank_name: string;
  online?: number | null;
  tai_quay?: number | null;
  difference?: number;
  the_chap_min?: number | null;
  the_chap_max?: number | null;
  tin_chap_min?: number | null;
  tin_chap_max?: number | null;
  loan_diff?: number;
  scraped_at?: string;
}

export default function SoSanhPage() {
  const [activeTab, setActiveTab] = useState<TabType>("deposit");
  const [depositTerm, setDepositTerm] = useState<number>(12);
  const [loanMetric, setLoanMetric] = useState<"min_rate" | "range">("min_rate");
  const [comparisonData, setComparisonData] = useState<ComparisonData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch deposit comparison data
  const fetchDepositComparison = async () => {
    try {
      setLoading(true);
      setError(null);

      const [onlineData, counterData] = await Promise.all([
        api.latest({
          series_code: "deposit_online",
          term_months: depositTerm,
          sort: "rate_desc",
        }),
        api.latest({
          series_code: "deposit_tai_quay",
          term_months: depositTerm,
          sort: "rate_desc",
        }),
      ]);

      // Merge data by bank_name
      const merged: ComparisonData[] = [];
      const bankMap = new Map<string, ComparisonData>();

      // Process online data
      onlineData.rows.forEach(item => {
        bankMap.set(item.bank_name, {
          bank_name: item.bank_name,
          online: item.rate_pct,
          scraped_at: item.scraped_at,
        });
      });

      // Process counter data and calculate difference
      counterData.rows.forEach(item => {
        const existing = bankMap.get(item.bank_name) || {
          bank_name: item.bank_name,
        };
        existing.tai_quay = item.rate_pct;
        if (existing.online !== null && existing.online !== undefined && existing.tai_quay !== null) {
          existing.difference = existing.online - existing.tai_quay;
        }
        bankMap.set(item.bank_name, existing);
      });

      // Convert to array and sort by difference (highest first)
      const sorted = Array.from(bankMap.values())
        .filter(item => item.difference !== undefined && item.online !== null && item.tai_quay !== null)
        .sort((a, b) => (b.difference || 0) - (a.difference || 0))
        .slice(0, 15);

      setComparisonData(sorted);
    } catch (err: any) {
      setError(err.message || "Không thể tải dữ liệu so sánh");
    } finally {
      setLoading(false);
    }
  };

  // Fetch loan comparison data
  const fetchLoanComparison = async () => {
    try {
      setLoading(true);
      setError(null);

      const [securedData, unsecuredData] = await Promise.all([
        api.latest({
          series_code: "loan_the_chap",
          sort: "rate_asc",
        }),
        api.latest({
          series_code: "loan_tin_chap",
          sort: "rate_asc",
        }),
      ]);

      // Merge data by bank_name
      const bankMap = new Map<string, ComparisonData>();

      // Process secured data
      securedData.rows.forEach(item => {
        bankMap.set(item.bank_name, {
          bank_name: item.bank_name,
          the_chap_min: item.rate_min_pct,
          the_chap_max: item.rate_max_pct,
          scraped_at: item.scraped_at,
        });
      });

      // Process unsecured data and calculate difference
      unsecuredData.rows.forEach(item => {
        const existing = bankMap.get(item.bank_name) || {
          bank_name: item.bank_name,
        };
        existing.tin_chap_min = item.rate_min_pct;
        existing.tin_chap_max = item.rate_max_pct;

        // Calculate difference based on selected metric
        if (loanMetric === "min_rate") {
          if (existing.the_chap_min !== null && existing.the_chap_min !== undefined && existing.tin_chap_min !== null) {
            existing.loan_diff = existing.tin_chap_min - existing.the_chap_min;
          }
        } else {
          // Calculate range difference
          const securedRange = existing.the_chap_max && existing.the_chap_min
            ? existing.the_chap_max - existing.the_chap_min
            : null;
          const unsecuredRange = existing.tin_chap_max && existing.tin_chap_min
            ? existing.tin_chap_max - existing.tin_chap_min
            : null;

          if (securedRange !== null && unsecuredRange !== null) {
            existing.loan_diff = unsecuredRange - securedRange;
          }
        }

        bankMap.set(item.bank_name, existing);
      });

      // Convert to array and sort
      const sorted = Array.from(bankMap.values())
        .filter(item => {
          if (loanMetric === "min_rate") {
            return item.loan_diff !== undefined &&
                   item.the_chap_min !== null &&
                   item.tin_chap_min !== null;
          } else {
            return item.loan_diff !== undefined &&
                   item.the_chap_min !== null &&
                   item.the_chap_max !== null &&
                   item.tin_chap_min !== null &&
                   item.tin_chap_max !== null;
          }
        })
        .sort((a, b) => (b.loan_diff || 0) - (a.loan_diff || 0))
        .slice(0, 15);

      setComparisonData(sorted);
    } catch (err: any) {
      setError(err.message || "Không thể tải dữ liệu so sánh");
    } finally {
      setLoading(false);
    }
  };

  // Fetch data when tab or filters change
  useEffect(() => {
    if (activeTab === "deposit") {
      fetchDepositComparison();
    } else {
      fetchLoanComparison();
    }
  }, [activeTab, depositTerm, loanMetric]);

  // Colors for bars
  const getBarColor = (index: number) => {
    const colors = [
      "#3b82f6", "#8b5cf6", "#ec4899", "#f43f5e", "#f97316",
      "#eab308", "#84cc16", "#22c55e", "#14b8a6", "#06b6d4",
      "#0ea5e9", "#6366f1", "#a855f7", "#d946ef", "#f43f5e"
    ];
    return colors[index % colors.length];
  };

  return (
    <div>
      <TopTabs basePath="/lai-suat" />
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white mb-2">So sánh lãi suất</h1>
        <p className="text-sm text-white/60">
          So sánh chênh lệch lãi suất giữa các kênh và loại hình vay
        </p>
      </div>

      {/* Tab Switcher */}
      <GlassCard className="mb-6">
        <div className="flex space-x-2">
          <button
            onClick={() => setActiveTab("deposit")}
            className={`px-6 py-3 rounded-lg font-medium transition-all ${
              activeTab === "deposit"
                ? "bg-blue-500 text-white"
                : "bg-white/5 text-white/60 hover:bg-white/10"
            }`}
          >
            Tiền gửi: Online vs Tại quầy
          </button>
          <button
            onClick={() => setActiveTab("loan")}
            className={`px-6 py-3 rounded-lg font-medium transition-all ${
              activeTab === "loan"
                ? "bg-blue-500 text-white"
                : "bg-white/5 text-white/60 hover:bg-white/10"
            }`}
          >
            Khoản vay: Thế chấp vs Tín chấp
          </button>
        </div>
      </GlassCard>

      {/* Filters */}
      <GlassCard className="mb-6">
        {activeTab === "deposit" ? (
          <div className="flex items-center gap-4">
            <label className="text-sm text-white/60">Kỳ hạn:</label>
            <select
              value={depositTerm}
              onChange={(e) => setDepositTerm(Number(e.target.value))}
              className="glass-input px-4 py-2 rounded-lg text-white text-sm"
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
        ) : (
          <div className="flex items-center gap-4">
            <label className="text-sm text-white/60">So sánh theo:</label>
            <select
              value={loanMetric}
              onChange={(e) => setLoanMetric(e.target.value as "min_rate" | "range")}
              className="glass-input px-4 py-2 rounded-lg text-white text-sm"
            >
              <option value="min_rate">So sánh lãi tối thiểu</option>
              <option value="range">So sánh biên độ</option>
            </select>
          </div>
        )}
      </GlassCard>

      {/* Error State */}
      {error && (
        <GlassCard className="mb-6">
          <p className="text-red-400 text-lg mb-2">Lỗi</p>
          <p className="text-white/60">{error}</p>
        </GlassCard>
      )}

      {/* Loading State */}
      {loading && !error && comparisonData.length === 0 && (
        <GlassCard>
          <div className="flex items-center justify-center h-64">
            <div className="text-white/60">Đang tải dữ liệu...</div>
          </div>
        </GlassCard>
      )}

      {/* Empty State */}
      {!loading && !error && comparisonData.length === 0 && (
        <GlassCard>
          <div className="flex flex-col items-center justify-center h-64 text-center px-8">
            <p className="text-white/70 text-lg mb-2">Chưa có dữ liệu để so sánh</p>
            <p className="text-white/40 text-sm">
              {activeTab === "deposit"
                ? "Cần có dữ liệu cả Online và Tại quầy cho cùng ngân hàng/kỳ hạn."
                : "Cần có dữ liệu cả Thế chấp và Tín chấp cho cùng ngân hàng."}
            </p>
          </div>
        </GlassCard>
      )}

      {/* Content */}
      {!loading && !error && comparisonData.length > 0 && (
        <>
          {/* Chart */}
          <GlassCard className="mb-6">
            <h2 className="text-xl font-semibold text-white mb-4">
              {activeTab === "deposit"
                ? `Top 15 ngân hàng có chênh lệch cao nhất (${depositTerm} tháng)`
                : loanMetric === "min_rate"
                ? "Top 15 ngân hàng có chênh lệch lãi tối thiểu cao nhất"
                : "Top 15 ngân hàng có chênh lệch biên độ cao nhất"}
            </h2>
            <ResponsiveContainer width="100%" height={400}>
              <BarChart data={comparisonData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis
                  dataKey="bank_name"
                  stroke="rgba(255,255,255,0.6)"
                  style={{ fontSize: '12px' }}
                  angle={-45}
                  textAnchor="end"
                  height={100}
                />
                <YAxis
                  stroke="rgba(255,255,255,0.6)"
                  style={{ fontSize: '12px' }}
                  label={{ value: '%', angle: -90, position: 'insideLeft', fill: 'rgba(255,255,255,0.6)' }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "rgba(15, 23, 42, 0.9)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: "12px",
                  }}
                  labelStyle={{ color: "rgba(255,255,255,0.8)" }}
                  formatter={(value: number) => formatRate(value)}
                />
                <Legend />
                <Bar
                  dataKey={activeTab === "deposit" ? "difference" : "loan_diff"}
                  name={activeTab === "deposit" ? "Chênh lệch (%)" : loanMetric === "min_rate" ? "Chênh lệch lãi (%)" : "Chênh lệch biên độ (%)"}
                  fill="#3b82f6"
                >
                  {comparisonData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={getBarColor(index)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </GlassCard>

          {/* Table */}
          <GlassCard>
            <h2 className="text-xl font-semibold text-white mb-4">
              Chi tiết chênh lệch
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left py-3 px-4 text-sm font-medium text-white/60">
                      Ngân hàng
                    </th>
                    {activeTab === "deposit" ? (
                      <>
                        <th className="text-right py-3 px-4 text-sm font-medium text-white/60">
                          Online
                        </th>
                        <th className="text-right py-3 px-4 text-sm font-medium text-white/60">
                          Tại quầy
                        </th>
                      </>
                    ) : (
                      <>
                        <th className="text-right py-3 px-4 text-sm font-medium text-white/60">
                          Thế chấp
                        </th>
                        <th className="text-right py-3 px-4 text-sm font-medium text-white/60">
                          Tín chấp
                        </th>
                      </>
                    )}
                    <th className="text-right py-3 px-4 text-sm font-medium text-white/60">
                      Chênh lệch
                    </th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-white/60">
                      Cập nhật
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {comparisonData.map((item, index) => (
                    <tr key={index} className="border-b border-white/5 hover:bg-white/5">
                      <td className="py-3 px-4 text-white">{item.bank_name}</td>
                      {activeTab === "deposit" ? (
                        <>
                          <td className="py-3 px-4 text-right">
                            <span className="text-green-400 font-semibold">
                              {formatRate(item.online)}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <span className="text-white/80 font-semibold">
                              {formatRate(item.tai_quay)}
                            </span>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="py-3 px-4 text-right">
                            {loanMetric === "min_rate" ? (
                              <span className="text-green-400 font-semibold">
                                {formatRate(item.the_chap_min)}
                              </span>
                            ) : (
                              <span className="text-white/80">
                                {formatRate(item.the_chap_min)} - {formatRate(item.the_chap_max)}
                              </span>
                            )}
                          </td>
                          <td className="py-3 px-4 text-right">
                            {loanMetric === "min_rate" ? (
                              <span className="text-red-400 font-semibold">
                                {formatRate(item.tin_chap_min)}
                              </span>
                            ) : (
                              <span className="text-white/80">
                                {formatRate(item.tin_chap_min)} - {formatRate(item.tin_chap_max)}
                              </span>
                            )}
                          </td>
                        </>
                      )}
                      <td className="py-3 px-4 text-right">
                        <span
                          className={`font-semibold ${
                            ((activeTab === "deposit" ? item.difference : item.loan_diff) || 0) > 0
                              ? "text-green-400"
                              : "text-red-400"
                          }`}
                        >
                          {activeTab === "deposit"
                            ? formatRate(item.difference ?? null)
                            : formatRate(item.loan_diff ?? null)}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right text-sm text-white/40">
                        {item.scraped_at ? formatDate(item.scraped_at) : "N/A"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </>
      )}

      {/* No Data */}
      {!loading && !error && comparisonData.length === 0 && (
        <GlassCard>
          <div className="text-center py-12">
            <p className="text-white/60 text-lg">
              Không có dữ liệu so sánh cho lựa chọn này
            </p>
          </div>
        </GlassCard>
      )}
    </div>
  );
}
