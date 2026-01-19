"use client";

import { useEffect, useState } from "react";
import { TopTabs } from "@/components/TopTabs";
import { GlassCard } from "@/components/GlassCard";
import { api, LatestRateItem, MetaLatestResponse } from "@/lib/api";

// Helper functions
const formatDate = (dateStr: string | null) => {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  return date.toLocaleDateString("vi-VN");
};

const formatRate = (rate: number | null | undefined) => {
  if (rate == null) return "N/A";  // Catches both null and undefined
  return rate.toFixed(2) + "%";
};

export default function HomePage() {
  const [depositSeries, setDepositSeries] = useState<"deposit_online" | "deposit_tai_quay">("deposit_online");
  const [depositTerm, setDepositTerm] = useState<number>(12);
  const [loanSeries, setLoanSeries] = useState<"loan_the_chap" | "loan_tin_chap">("loan_the_chap");
  const [depositData, setDepositData] = useState<LatestRateItem[]>([]);
  const [loanData, setLoanData] = useState<LatestRateItem[]>([]);
  const [kpis, setKpis] = useState<{ title: string; value: string; subtitle?: string }[]>([]);
  const [meta, setMeta] = useState<MetaLatestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch deposit data
      const depositResult = await api.latest({
        series_code: depositSeries,
        term_months: depositTerm,
        sort: "rate_desc",
      });
      setDepositData(depositResult.rows);

      // Fetch loan data
      const loanResult = await api.latest({
        series_code: loanSeries,
        sort: "rate_asc",
      });
      setLoanData(loanResult.rows);

      // Fetch meta for KPIs
      const metaResult = await api.metaLatest();

      // Fetch top rates for KPIs
      const [online12m, counter12m, secured, unsecured] = await Promise.all([
        api.latest({ series_code: "deposit_online", term_months: 12, sort: "rate_desc" }),
        api.latest({ series_code: "deposit_tai_quay", term_months: 12, sort: "rate_desc" }),
        api.latest({ series_code: "loan_the_chap", sort: "rate_asc" }),
        api.latest({ series_code: "loan_tin_chap", sort: "rate_asc" }),
      ]);

      setKpis([
        {
          title: "Tiền gửi cao nhất (12T - Online)",
          value: online12m.rows.length > 0 ? formatRate(online12m.rows[0]?.rate_pct) : "N/A",
          subtitle: online12m.rows[0]?.bank_name || "Chưa có dữ liệu",
        },
        {
          title: "Tiền gửi cao nhất (12T - Tại quầy)",
          value: counter12m.rows.length > 0 ? formatRate(counter12m.rows[0]?.rate_pct) : "N/A",
          subtitle: counter12m.rows[0]?.bank_name || "Chưa có dữ liệu",
        },
        {
          title: "Vay thấp nhất (Thế chấp)",
          value: secured.rows.length > 0 ? formatRate(secured.rows[0]?.rate_min_pct) : "N/A",
          subtitle: secured.rows[0]?.bank_name || "Chưa có dữ liệu",
        },
        {
          title: "Vay thấp nhất (Tín chấp)",
          value: unsecured.rows.length > 0 ? formatRate(unsecured.rows[0]?.rate_min_pct) : "N/A",
          subtitle: unsecured.rows[0]?.bank_name || "Chưa có dữ liệu",
        },
      ]);

      setMeta(metaResult);
    } catch (err: any) {
      setError(err.message || "Không thể tải dữ liệu");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [depositSeries, depositTerm, loanSeries]);

  if (loading && !error) {
    return (
      <div>
        <TopTabs />
        <div className="flex items-center justify-center h-64">
          <div className="text-white/60">Đang tải...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <TopTabs />
        <div className="glass-card rounded-2xl p-8 text-center">
          <p className="text-red-400 text-lg mb-4">Lỗi: {error}</p>
          <p className="text-white/60">
            Không thể kết nối API. Hãy chắc chắn backend đang chạy trên port 8001
          </p>
        </div>
      </div>
    );
  }

  const seriesLabel = depositSeries === "deposit_online" ? "Online" : "Tại quầy";
  const loanLabel = loanSeries === "loan_the_chap" ? "Thế chấp" : "Tín chấp";

  return (
    <div>
      <TopTabs />
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white mb-2">Bảng điều khiển lãi suất</h1>
        {meta?.latest_scraped_at && (
          <p className="text-sm text-white/60">
            Cập nhật lần cuối: {formatDate(meta.latest_scraped_at)}
          </p>
        )}
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {kpis.map((kpi, index) => (
          <GlassCard key={index} className="flex flex-col">
            <p className="text-sm text-white/60 mb-2">{kpi.title}</p>
            <p className="text-3xl font-bold text-white mb-1">{kpi.value}</p>
            {kpi.subtitle && <p className="text-sm text-white/40">{kpi.subtitle}</p>}
          </GlassCard>
        ))}
      </div>

      {/* Deposit and Loan Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Deposit Table */}
        <div>
          <div className="mb-4 flex items-center gap-4">
            <select
              value={depositSeries}
              onChange={(e) => setDepositSeries(e.target.value as any)}
              className="glass-input px-4 py-2 rounded-lg text-white text-sm"
            >
              <option value="deposit_online">Online</option>
              <option value="deposit_tai_quay">Tại quầy</option>
            </select>
            <select
              value={depositTerm}
              onChange={(e) => setDepositTerm(Number(e.target.value))}
              className="glass-input px-4 py-2 rounded-lg text-white text-sm"
            >
              <option value={1}>1 tháng</option>
              <option value={3}>3 tháng</option>
              <option value={6}>6 tháng</option>
              <option value={12}>12 tháng</option>
              <option value={24}>24 tháng</option>
              <option value={36}>36 tháng</option>
            </select>
          </div>
          <GlassCard>
            <h2 className="text-xl font-semibold text-white mb-4">
              Lãi suất tiền gửi ({seriesLabel} - {depositTerm} tháng)
            </h2>
            {depositData.length === 0 ? (
              <div className="text-center py-12">
                <p className="text-white/60 text-lg mb-2">Không có dữ liệu</p>
                <p className="text-white/40 text-sm">
                  Không tìm thấy dữ liệu cho kỳ hạn này.
                </p>
              </div>
            ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left py-3 px-4 text-sm font-medium text-white/60">Ngân hàng</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-white/60">Lãi suất (%)</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-white/60">Cập nhật</th>
                  </tr>
                </thead>
                <tbody>
                  {depositData.map((item) => (
                    <tr key={item.bank_name} className="border-b border-white/5 hover:bg-white/5">
                      <td className="py-3 px-4 text-white">{item.bank_name}</td>
                      <td className="py-3 px-4 text-right">
                        <span className="text-white font-semibold">
                          {formatRate(item.rate_pct)}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right text-sm text-white/40">
                        {formatDate(item.scraped_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            )}
          </GlassCard>
        </div>

        {/* Loan Table */}
        <div>
          <div className="mb-4">
            <select
              value={loanSeries}
              onChange={(e) => setLoanSeries(e.target.value as any)}
              className="glass-input px-4 py-2 rounded-lg text-white text-sm"
            >
              <option value="loan_the_chap">Thế chấp</option>
              <option value="loan_tin_chap">Tín chấp</option>
            </select>
          </div>
          <GlassCard>
            <h2 className="text-xl font-semibold text-white mb-4">
              Lãi suất vay ({loanLabel})
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left py-3 px-4 text-sm font-medium text-white/60">Ngân hàng</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-white/60">Thấp (%)</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-white/60">Cao (%)</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-white/60">Cập nhật</th>
                  </tr>
                </thead>
                <tbody>
                  {loanData.map((item) => (
                    <tr key={item.bank_name} className="border-b border-white/5 hover:bg-white/5">
                      <td className="py-3 px-4 text-white">{item.bank_name}</td>
                      <td className="py-3 px-4 text-right">
                        <span className="text-green-400 font-semibold">
                          {formatRate(item.rate_min_pct)}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <span className="text-red-400 font-semibold">
                          {formatRate(item.rate_max_pct)}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right text-sm text-white/40">
                        {formatDate(item.scraped_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
