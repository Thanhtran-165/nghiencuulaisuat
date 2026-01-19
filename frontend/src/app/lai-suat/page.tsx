"use client";

import { useEffect, useState } from "react";
import { TopTabs } from "@/components/TopTabs";
import { GlassCard } from "@/components/GlassCard";
import { api, LatestRateItem, MetaLatestResponse } from "@/lib/api";
import { BankAveragesChart, BankAveragesPoint } from "@/components/BankAveragesChart";

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
  const [depositSeries, setDepositSeries] = useState<"deposit_online" | "deposit_tai_quay">("deposit_tai_quay");
  const [depositTerm, setDepositTerm] = useState<number>(12);
  const [loanSeries, setLoanSeries] = useState<"loan_the_chap" | "loan_tin_chap">("loan_the_chap");
  const [depositData, setDepositData] = useState<LatestRateItem[]>([]);
  const [loanData, setLoanData] = useState<LatestRateItem[]>([]);
  const [kpis, setKpis] = useState<{ title: string; value: string; subtitle?: string }[]>([]);
  const [meta, setMeta] = useState<MetaLatestResponse | null>(null);
  const [avgLatest, setAvgLatest] = useState<any>(null);
  const [avgSeries, setAvgSeries] = useState<BankAveragesPoint[]>([]);
  const [avgLoading, setAvgLoading] = useState(false);
  const [avgError, setAvgError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const lastNonNull = <K extends keyof BankAveragesPoint>(key: K) => {
    for (let i = avgSeries.length - 1; i >= 0; i--) {
      const v = avgSeries[i]?.[key];
      if (v != null) return { idx: i, point: avgSeries[i] };
    }
    return null;
  };

  const fetchAverages = async () => {
    try {
      setAvgLoading(true);
      setAvgError(null);
      const latestRes = await fetch("/api/lai-suat/averages/latest?deposit_term_months=12&align_common_date=true", {
        cache: "no-store",
      });
      if (!latestRes.ok) {
        throw new Error("Không thể tải dữ liệu trung bình (backend chưa cập nhật hoặc đang tắt).");
      }
      const latestJson = await latestRes.json();
      setAvgLatest(latestJson);

      const end = new Date();
      const start = new Date(end.getTime() - 365 * 24 * 60 * 60 * 1000);
      const iso = (d: Date) => d.toISOString().slice(0, 10);
      const seriesRes = await fetch(
        `/api/lai-suat/averages/timeseries?start_date=${encodeURIComponent(iso(start))}&end_date=${encodeURIComponent(
          iso(end)
        )}&deposit_term_months=12`,
        { cache: "no-store" }
      );
      if (!seriesRes.ok) {
        throw new Error("Không thể tải chuỗi lịch sử trung bình.");
      }
      const seriesJson = await seriesRes.json();
      setAvgSeries(seriesJson || []);
    } catch (e: any) {
      setAvgError(e?.message || "Không thể tải dữ liệu trung bình.");
    } finally {
      setAvgLoading(false);
    }
  };

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
      const [counter12m, online12m, secured, unsecured] = await Promise.all([
        api.latest({ series_code: "deposit_tai_quay", term_months: 12, sort: "rate_desc" }),
        api.latest({ series_code: "deposit_online", term_months: 12, sort: "rate_desc" }),
        api.latest({ series_code: "loan_the_chap", sort: "rate_asc" }),
        api.latest({ series_code: "loan_tin_chap", sort: "rate_asc" }),
      ]);

      setKpis([
        {
          title: "Tiền gửi cao nhất (12T - Tại quầy · Timo)",
          value: counter12m.rows.length > 0 ? formatRate(counter12m.rows[0]?.rate_pct) : "N/A",
          subtitle: counter12m.rows[0]?.bank_name || "Chưa có dữ liệu",
        },
        {
          title: "Tiền gửi cao nhất (12T - Online · 24hmoney)",
          value: online12m.rows.length > 0 ? formatRate(online12m.rows[0]?.rate_pct) : "N/A",
          subtitle: online12m.rows[0]?.bank_name || "Chưa có dữ liệu",
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

  useEffect(() => {
    fetchAverages();
  }, []);

  if (loading && !error) {
    return (
      <div>
        <TopTabs basePath="/lai-suat" />
        <div className="flex items-center justify-center h-64">
          <div className="text-white/60">Đang tải...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <TopTabs basePath="/lai-suat" />
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
  const avgAsOf = avgLatest?.as_of_date as string | undefined;
  const depLatest = avgLatest?.deposit_latest_date as string | undefined;
  const loanLatest = avgLatest?.loan_latest_date as string | undefined;

  const avgDepNow = (avgLatest?.deposit_avg_12m as number | null | undefined) ?? null;
  const avgLoanNow = (avgLatest?.loan_avg as number | null | undefined) ?? null;

  const depLast = lastNonNull("deposit_avg_12m");
  const depPrev = depLast && depLast.idx > 0 ? (() => {
    for (let i = depLast.idx - 1; i >= 0; i--) {
      const v = avgSeries[i]?.deposit_avg_12m;
      if (v != null) return avgSeries[i];
    }
    return null;
  })() : null;
  const avgDepDeltaBps =
    depLast?.point?.deposit_avg_12m != null && depPrev?.deposit_avg_12m != null
      ? (depLast.point.deposit_avg_12m - depPrev.deposit_avg_12m) * 100
      : null;

  const loanLast = lastNonNull("loan_avg");
  const loanPrev = loanLast && loanLast.idx > 0 ? (() => {
    for (let i = loanLast.idx - 1; i >= 0; i--) {
      const v = avgSeries[i]?.loan_avg;
      if (v != null) return avgSeries[i];
    }
    return null;
  })() : null;
  const avgLoanDeltaBps =
    loanLast?.point?.loan_avg != null && loanPrev?.loan_avg != null ? (loanLast.point.loan_avg - loanPrev.loan_avg) * 100 : null;

  return (
    <div>
      <TopTabs basePath="/lai-suat" />
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white mb-2">Bảng điều khiển lãi suất</h1>
        <div className="space-y-1 text-sm text-white/60">
          {meta?.latest_scraped_at ? <div>Crawl gần nhất: {formatDate(meta.latest_scraped_at)}</div> : null}
          {depLatest || loanLatest ? (
            <div>
              Kỳ dữ liệu: Tiền gửi {depLatest ? formatDate(depLatest) : "—"} • Cho vay{" "}
              {loanLatest ? formatDate(loanLatest) : "—"}
              {avgAsOf ? <> • Trung bình dùng: {formatDate(avgAsOf)}</> : null}
            </div>
          ) : null}
          {avgLatest?.note ? <div className="text-white/40">{avgLatest.note}</div> : null}
          {avgError ? <div className="text-rose-200">{avgError}</div> : null}
        </div>
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

      {/* Average charts */}
      <div className="mb-8 space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <GlassCard className="space-y-2">
            <div className="text-white/60 text-sm">Lãi suất tiền gửi trung bình (12T)</div>
            <div className="text-white text-3xl font-semibold">
              {avgDepNow != null ? formatRate(avgDepNow) : "—"}
            </div>
            <div className="text-white/50 text-sm">
              {avgDepDeltaBps != null ? `Δ ${(avgDepDeltaBps > 0 ? "+" : "") + avgDepDeltaBps.toFixed(0)} bps` : "—"}
            </div>
          </GlassCard>
          <GlassCard className="space-y-2">
            <div className="text-white/60 text-sm">Lãi suất vay trung bình</div>
            <div className="text-white text-3xl font-semibold">{avgLoanNow != null ? formatRate(avgLoanNow) : "—"}</div>
            <div className="text-white/50 text-sm">
              {avgLoanDeltaBps != null ? `Δ ${(avgLoanDeltaBps > 0 ? "+" : "") + avgLoanDeltaBps.toFixed(0)} bps` : "—"}
            </div>
          </GlassCard>
        </div>
        {avgSeries.length ? (
          <BankAveragesChart title="Biểu đồ lãi suất trung bình (quan sát ~1 năm)" data={avgSeries} />
        ) : (
          <GlassCard>
            <div className="text-white/60">{avgLoading ? "Đang tải biểu đồ…" : "Chưa có dữ liệu trung bình để vẽ biểu đồ."}</div>
          </GlassCard>
        )}
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
              <option value="deposit_tai_quay">Tại quầy (Timo)</option>
              <option value="deposit_online">Online (24hmoney)</option>
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
	                    <th className="text-right py-3 px-4 text-sm font-medium text-white/60">Kỳ dữ liệu</th>
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
	                        {formatDate(item.observed_day || item.scraped_at)}
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
	                    <th className="text-right py-3 px-4 text-sm font-medium text-white/60">Kỳ dữ liệu</th>
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
	                        {formatDate(item.observed_day || item.scraped_at)}
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
