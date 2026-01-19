"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { TopTabs } from "@/components/TopTabs";
import { GlassCard } from "@/components/GlassCard";
import { BankAveragesChart, BankAveragesPoint } from "@/components/BankAveragesChart";
import { bondlabApi, LeadLagResult } from "@/lib/bondlabApi";

function formatDate(dateStr?: string | null) {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("vi-VN");
}

function formatRate(rate?: number | null) {
  if (rate == null) return "—";
  return `${rate.toFixed(2)}%`;
}

function formatBps(delta?: number | null) {
  if (delta == null) return "—";
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(0)} bps`;
}

function seriesDeltaBps(series: BankAveragesPoint[], key: "deposit_avg_12m" | "loan_avg", lookback: number) {
  if (!series.length) return null;
  let lastIdx = -1;
  for (let i = series.length - 1; i >= 0; i--) {
    if (series[i]?.[key] != null) {
      lastIdx = i;
      break;
    }
  }
  const last = lastIdx >= 0 ? series[lastIdx]?.[key] : null;
  const prev = lastIdx - lookback >= 0 ? series[lastIdx - lookback]?.[key] : null;
  if (last == null || prev == null) return null;
  return (last - prev) * 100;
}

function interpretLeadLag(
  res: LeadLagResult | null,
  xLabel: string,
  yLabel: string
): { headline: string; detail: string } {
  if (!res || res.best_lag == null || res.best_corr == null) {
    return { headline: "Chưa đủ dữ liệu để kết luận.", detail: "Hãy mở rộng khoảng thời gian hoặc chờ thêm dữ liệu." };
  }
  const lag = res.best_lag;
  const corr = res.best_corr;
  const whoLeads =
    lag > 0
      ? `${xLabel} thường đi trước ${yLabel} ~${lag} phiên`
      : lag < 0
        ? `${yLabel} thường đi trước ${xLabel} ~${Math.abs(lag)} phiên`
        : "Hai chuỗi gần như đồng thời (lag=0)";
  const sameOpp = corr >= 0 ? "cùng chiều" : "ngược chiều";
  const n = res.best_n_pairs ?? null;
  const p = res.best_p_value_adj ?? null;
  return {
    headline: `${whoLeads} (${sameOpp})`,
    detail: `corr=${corr.toFixed(3)} • n=${n ?? "—"} • p(adj)=${p != null ? p.toFixed(4) : "—"}`,
  };
}

type Pair = { id: string; title: string; x: string; y: string };

const PAIRS: Pair[] = [
  { id: "ib_dep", title: "IB O/N ↔ Tiền gửi TB 12T", x: "ib_on", y: "bank_deposit_avg_12m" },
  { id: "ib_loan", title: "IB O/N ↔ Cho vay TB", x: "ib_on", y: "bank_loan_avg" },
  { id: "y10_dep", title: "VN10Y ↔ Tiền gửi TB 12T", x: "yield_10y", y: "bank_deposit_avg_12m" },
  { id: "y10_loan", title: "VN10Y ↔ Cho vay TB", x: "yield_10y", y: "bank_loan_avg" },
  { id: "y2_dep", title: "VN2Y ↔ Tiền gửi TB 12T", x: "yield_2y", y: "bank_deposit_avg_12m" },
  { id: "y2_loan", title: "VN2Y ↔ Cho vay TB", x: "yield_2y", y: "bank_loan_avg" },
  { id: "slope_dep", title: "Độ dốc (10Y–2Y) ↔ Tiền gửi TB 12T", x: "slope_10y_2y", y: "bank_deposit_avg_12m" },
  { id: "slope_loan", title: "Độ dốc (10Y–2Y) ↔ Cho vay TB", x: "slope_10y_2y", y: "bank_loan_avg" },
];

export default function LaiSuatNghienCuuPage() {
  const [start, setStart] = useState(() => {
    const end = new Date();
    const s = new Date(end.getTime() - 365 * 24 * 60 * 60 * 1000);
    return s.toISOString().slice(0, 10);
  });
  const [end, setEnd] = useState(() => new Date().toISOString().slice(0, 10));

  const [avgSeries, setAvgSeries] = useState<BankAveragesPoint[]>([]);
  const [avgLoading, setAvgLoading] = useState(false);

  const [seriesCatalog, setSeriesCatalog] = useState<Record<string, string>>({});
  const [leadLagMap, setLeadLagMap] = useState<Record<string, LeadLagResult | null>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const depDelta14 = useMemo(() => seriesDeltaBps(avgSeries, "deposit_avg_12m", 14), [avgSeries]);
  const depDelta60 = useMemo(() => seriesDeltaBps(avgSeries, "deposit_avg_12m", 60), [avgSeries]);
  const loanDelta14 = useMemo(() => seriesDeltaBps(avgSeries, "loan_avg", 14), [avgSeries]);
  const loanDelta60 = useMemo(() => seriesDeltaBps(avgSeries, "loan_avg", 60), [avgSeries]);

  const avgLast = useMemo(() => {
    let dep: number | null = null;
    let loan: number | null = null;
    for (let i = avgSeries.length - 1; i >= 0; i--) {
      if (dep == null && avgSeries[i]?.deposit_avg_12m != null) dep = avgSeries[i].deposit_avg_12m ?? null;
      if (loan == null && avgSeries[i]?.loan_avg != null) loan = avgSeries[i].loan_avg ?? null;
      if (dep != null && loan != null) break;
    }
    return { deposit_avg_12m: dep, loan_avg: loan };
  }, [avgSeries]);

  useEffect(() => {
    const load = async () => {
      try {
        setAvgLoading(true);
        setErr(null);
        const res = await fetch(
          `/api/lai-suat/averages/timeseries?start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}&deposit_term_months=12`,
          { cache: "no-store" }
        );
        if (!res.ok) throw new Error("Không thể tải chuỗi trung bình.");
        const data = await res.json();
        setAvgSeries(data || []);
      } catch (e: any) {
        setErr(e?.message || "Có lỗi khi tải dữ liệu.");
      } finally {
        setAvgLoading(false);
      }
    };
    load();
  }, [start, end]);

  useEffect(() => {
    const loadCatalog = async () => {
      try {
        const list = await bondlabApi.causalitySeries();
        const m: Record<string, string> = {};
        for (const s of list) m[s.id] = s.label || s.id;
        setSeriesCatalog(m);
      } catch {
        // ok
      }
    };
    loadCatalog();
  }, []);

  const runLeadLagBatch = async () => {
    try {
      setBusy(true);
      setErr(null);
      const results = await Promise.all(
        PAIRS.map(async (p) => {
          try {
            const r = await bondlabApi.causalityLeadLag({
              x: p.x,
              y: p.y,
              start_date: start,
              end_date: end,
              max_lag: 20,
              diff: true,
            });
            return [p.id, r] as const;
          } catch {
            return [p.id, null] as const;
          }
        })
      );
      const m: Record<string, LeadLagResult | null> = {};
      for (const [id, r] of results) m[id] = r;
      setLeadLagMap(m);
    } catch (e: any) {
      setErr(e?.message || "Không thể chạy lead‑lag.");
    } finally {
      setBusy(false);
    }
  };

  const label = (id: string) => seriesCatalog[id] || id;

  return (
    <div>
      <TopTabs basePath="/lai-suat" />
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white mb-2">Nghiên cứu xu hướng lãi suất</h1>
        <div className="text-sm text-white/60">
          Trang này diễn giải theo hướng “từ số → thông tin” (mô tả thống kê, không khẳng định nhân quả).
        </div>
      </div>

      <GlassCard className="mb-6">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <div className="text-white/60 text-xs mb-1">Từ ngày</div>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="glass-input px-3 py-2 rounded-lg text-white text-sm" />
          </div>
          <div>
            <div className="text-white/60 text-xs mb-1">Đến ngày</div>
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="glass-input px-3 py-2 rounded-lg text-white text-sm" />
          </div>
          <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" onClick={runLeadLagBatch} disabled={busy}>
            {busy ? "Đang chạy…" : "Chạy lead‑lag"}
          </button>
          <Link href="/causality" className="text-sm text-white/70 hover:text-white underline underline-offset-4">
            Mở Ai dẫn ai? →
          </Link>
        </div>
        {err ? <div className="mt-3 text-sm text-rose-200">{err}</div> : null}
        <div className="mt-3 text-xs text-white/50">
          “Phiên” ở đây là số điểm dữ liệu sau khi canonicalize (mỗi ngày 1 quan sát theo ưu tiên nguồn).
        </div>
      </GlassCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Tiền gửi TB 12T</div>
          <div className="text-white text-3xl font-semibold">{formatRate(avgLast.deposit_avg_12m ?? null)}</div>
          <div className="text-white/50 text-sm">Δ14 phiên: {formatBps(depDelta14)} • Δ60 phiên: {formatBps(depDelta60)}</div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Cho vay TB</div>
          <div className="text-white text-3xl font-semibold">{formatRate(avgLast.loan_avg ?? null)}</div>
          <div className="text-white/50 text-sm">Δ14 phiên: {formatBps(loanDelta14)} • Δ60 phiên: {formatBps(loanDelta60)}</div>
        </GlassCard>
      </div>

      <div className="mb-6">
        {avgSeries.length ? (
          <BankAveragesChart title="Chuỗi lãi suất trung bình (tiền gửi TB 12T & cho vay TB)" data={avgSeries} />
        ) : (
          <GlassCard>
            <div className="text-white/60">{avgLoading ? "Đang tải biểu đồ…" : "Chưa có dữ liệu để vẽ biểu đồ."}</div>
          </GlassCard>
        )}
      </div>

      <GlassCard>
        <div className="text-white font-semibold mb-3">Lead‑lag (mô tả thống kê)</div>
        <div className="text-white/60 text-sm mb-4">
          So theo thay đổi (Δ) để giảm ảnh hưởng xu hướng dài hạn. Kết quả phụ thuộc vào độ phủ dữ liệu & khoảng thời gian chọn.
        </div>

        <div className="space-y-3">
          {PAIRS.map((p) => {
            const res = leadLagMap[p.id] ?? null;
            const interp = interpretLeadLag(res, label(p.x), label(p.y));
            return (
              <div key={p.id} className="rounded-xl border border-white/10 bg-white/5 px-4 py-3">
                <div className="text-white/80 text-sm font-medium">{p.title}</div>
                <div className="text-white text-sm mt-1">{interp.headline}</div>
                <div className="text-white/50 text-xs mt-1">{interp.detail}</div>
              </div>
            );
          })}
        </div>

        <div className="mt-4 text-xs text-white/50">
          Định nghĩa “trung bình”:
          <ul className="list-disc pl-5 mt-1 space-y-1">
            <li>Tiền gửi TB 12T: mỗi ngày lấy lãi suất cao nhất theo từng ngân hàng (12 tháng) rồi lấy trung bình.</li>
            <li>Cho vay TB: mỗi ngày lấy lãi suất thấp nhất theo từng ngân hàng rồi lấy trung bình.</li>
          </ul>
        </div>
      </GlassCard>
    </div>
  );
}
