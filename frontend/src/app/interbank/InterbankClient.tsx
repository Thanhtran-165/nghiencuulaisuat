"use client";

import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import { bondlabApi, InterbankCompareResponse, InterbankRateRecord } from "@/lib/bondlabApi";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function fmtPct(value?: number | null) {
  if (value == null) return "—";
  return `${value.toFixed(2)}%`;
}

function fmtBps(value?: number | null) {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(0)} bps`;
}

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

function addDays(dateStr: string, deltaDays: number) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + deltaDays);
  return isoDate(d);
}

function fmtShortDate(iso?: string | null) {
  if (!iso) return "—";
  // Accept both YYYY-MM-DD and ISO datetime strings.
  const dt = new Date(iso);
  if (!Number.isNaN(dt.getTime())) {
    return dt.toLocaleDateString("vi-VN");
  }
  const [y, m, d] = iso.split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

function fmtDateTime(iso?: string | null) {
  if (!iso) return "—";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  return dt.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

const FIXED_TENORS = ["ON", "1W", "2W", "1M", "3M", "6M", "9M"];
const SIGNAL_TENORS = ["ON", "1W", "1M"];

type SignalRow = {
  tenor: string;
  latestRate: number | null;
  source: string | null;
  d7_bps: number | null;
  d14_bps: number | null;
  n: number;
  pairs14: number;
};

function calcDeltaBpsByObs(rows: InterbankRateRecord[], back: number) {
  const s = [...rows].sort((a, b) => a.date.localeCompare(b.date));
  const validPairs = Math.max(0, s.length - back);
  if (s.length <= back) return { deltaBps: null as number | null, validPairs };
  const now = s[s.length - 1]?.rate;
  const prev = s[s.length - 1 - back]?.rate;
  if (now == null || prev == null) return { deltaBps: null as number | null, validPairs };
  return { deltaBps: (now - prev) * 100.0, validPairs };
}

export function InterbankClient({ initialCompare }: { initialCompare: InterbankCompareResponse }) {
  const [compare, setCompare] = useState<InterbankCompareResponse>(initialCompare);

  const [tenor, setTenor] = useState<string>("ON");
  const [endDate, setEndDate] = useState<string>(initialCompare.today_date || "");
  const [startDate, setStartDate] = useState<string>(
    initialCompare.today_date ? addDays(initialCompare.today_date, -60) : ""
  );

  const [series, setSeries] = useState<InterbankRateRecord[]>([]);
  const [loadingSeries, setLoadingSeries] = useState(false);
  const [errorSeries, setErrorSeries] = useState<string | null>(null);

  const [latestSnapshot, setLatestSnapshot] = useState<InterbankRateRecord[]>([]);
  const [signalSeries, setSignalSeries] = useState<Record<string, InterbankRateRecord[]>>({});
  const [loadingSignals, setLoadingSignals] = useState(false);

  useEffect(() => {
    setCompare(initialCompare);
    if (initialCompare.today_date) {
      setEndDate(initialCompare.today_date);
      setStartDate(addDays(initialCompare.today_date, -60));
    }
  }, [initialCompare]);

  const tenors = useMemo(() => {
    const found = new Set((compare?.rows || []).map((r) => r.tenor_label));
    const base = FIXED_TENORS.filter((t) => found.has(t));
    const extras = Array.from(found).filter((t) => !FIXED_TENORS.includes(t)).sort();
    const list = [...base, ...extras];
    if (!list.includes("ON")) list.unshift("ON");
    return list;
  }, [compare]);

  const compareMap = useMemo(() => {
    const map: Record<string, { today?: number | null; prev?: number | null; change_bps?: number | null }> = {};
    for (const r of compare?.rows || []) {
      map[r.tenor_label] = { today: r.today_rate, prev: r.prev_rate, change_bps: r.change_bps };
    }
    return map;
  }, [compare]);

  const compareChartData = useMemo(() => {
    const hasAny = (compare?.rows || []).length > 0;
    const base = hasAny ? FIXED_TENORS : [];
    return base.map((t) => ({
      tenor: t,
      today: compareMap[t]?.today ?? null,
      prev: compareMap[t]?.prev ?? null,
    }));
  }, [compareMap, compare]);

  const snapshotSourceByTenor = useMemo(() => {
    const m: Record<string, string> = {};
    for (const r of latestSnapshot) m[r.tenor_label] = r.source;
    return m;
  }, [latestSnapshot]);

  const signalRows: SignalRow[] = useMemo(() => {
    return SIGNAL_TENORS.map((t) => {
      const rows = signalSeries[t] || [];
      const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
      const latest = sorted.length ? sorted[sorted.length - 1] : null;
      const d7 = calcDeltaBpsByObs(sorted, 7);
      const d14 = calcDeltaBpsByObs(sorted, 14);
      return {
        tenor: t,
        latestRate: latest?.rate ?? null,
        source: latest?.source ?? snapshotSourceByTenor[t] ?? null,
        d7_bps: d7.deltaBps,
        d14_bps: d14.deltaBps,
        n: sorted.length,
        pairs14: d14.validPairs,
      };
    });
  }, [signalSeries, snapshotSourceByTenor]);

  const seriesChartData = useMemo(() => {
    return [...series]
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((r) => ({
        date: r.date,
        rate: r.rate,
        source: r.source,
      }));
  }, [series]);

  async function loadSeries() {
    if (!startDate || !endDate) return;
    try {
      setLoadingSeries(true);
      setErrorSeries(null);
      const rows = await bondlabApi.interbankTimeseries({
        start_date: startDate,
        end_date: endDate,
        tenor,
      });
      setSeries(rows);
    } catch (e: any) {
      setErrorSeries(e?.message || "Không thể tải dữ liệu");
      setSeries([]);
    } finally {
      setLoadingSeries(false);
    }
  }

  async function loadSignals(targetEndDate: string) {
    if (!targetEndDate) return;
    const start = addDays(targetEndDate, -420);
    try {
      setLoadingSignals(true);
      const [latest, ...seriesList] = await Promise.all([
        bondlabApi.interbankLatest(),
        ...SIGNAL_TENORS.map((t) =>
          bondlabApi.interbankTimeseries({
            start_date: start,
            end_date: targetEndDate,
            tenor: t,
          })
        ),
      ]);

      setLatestSnapshot(latest);
      const next: Record<string, InterbankRateRecord[]> = {};
      SIGNAL_TENORS.forEach((t, idx) => {
        next[t] = seriesList[idx] || [];
      });
      setSignalSeries(next);
    } catch {
      setLatestSnapshot([]);
      setSignalSeries({});
    } finally {
      setLoadingSignals(false);
    }
  }

  async function refreshCompare() {
    const c = await bondlabApi.interbankCompare();
    setCompare(c);
    if (c.today_date) {
      setEndDate(c.today_date);
      setStartDate(addDays(c.today_date, -60));
      loadSignals(c.today_date);
    }
  }

  useEffect(() => {
    loadSeries();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenor]);

  useEffect(() => {
    if (compare?.today_date) loadSignals(compare.today_date);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compare?.today_date]);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Interbank</h1>
          <p className="text-white/60 mt-2">Lãi suất liên ngân hàng theo kỳ (nguồn SBV, fallback ABO nếu cần).</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10"
            onClick={() => refreshCompare()}
          >
            Làm mới snapshot
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <GlassCard className="space-y-3">
          <div>
            <div className="text-white font-semibold">So sánh kỳ hiện tại / kỳ trước</div>
            <div className="text-white/50 text-sm">
              Ngày áp dụng: {fmtShortDate(compare?.today_date)} • Kỳ trước: {fmtShortDate(compare?.prev_date)}
              {compare?.today_fetched_at ? <> • Cập nhật: {fmtDateTime(compare.today_fetched_at)}</> : null}
            </div>
          </div>

          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={compareChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="tenor" stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} />
              <YAxis
                stroke="rgba(255,255,255,0.6)"
                style={{ fontSize: "12px" }}
                tickFormatter={(v) => `${Number(v).toFixed(2)}%`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "rgba(15, 23, 42, 0.9)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: "12px",
                }}
                labelStyle={{ color: "rgba(255,255,255,0.8)" }}
                formatter={(value: any, name: any) => [fmtPct(value), name === "today" ? "Kỳ hiện tại" : "Kỳ trước"]}
              />
              <Legend />
              <Bar dataKey="today" name={`Kỳ hiện tại (${compare?.today_date || "—"})`} fill="#7c3aed" fillOpacity={0.35} />
              <Bar dataKey="prev" name={`Kỳ trước (${compare?.prev_date || "—"})`} fill="#60a5fa" fillOpacity={0.25} />
            </BarChart>
          </ResponsiveContainer>
        </GlassCard>

        <GlassCard className="space-y-3">
          <div className="text-white font-semibold">Bảng snapshot</div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px]">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Kỳ</th>
                  <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Kỳ hiện tại</th>
                  <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Kỳ trước</th>
                  <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Δ</th>
                </tr>
              </thead>
              <tbody>
                {FIXED_TENORS.map((t) => (
                  <tr key={t} className="border-b border-white/5 hover:bg-white/5">
                    <td className="py-2 px-3 text-white">{t}</td>
                    <td className="py-2 px-3 text-right text-white/90">{fmtPct(compareMap[t]?.today ?? null)}</td>
                    <td className="py-2 px-3 text-right text-white/60">{fmtPct(compareMap[t]?.prev ?? null)}</td>
                    <td className="py-2 px-3 text-right text-white/90 font-semibold">{fmtBps(compareMap[t]?.change_bps ?? null)}</td>
                  </tr>
                ))}
                {!compare?.rows?.length ? (
                  <tr>
                    <td className="py-6 px-3 text-white/60" colSpan={4}>
                      Chưa có dữ liệu interbank.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </GlassCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="space-y-2">
          <div className="text-white font-semibold">Tín hiệu ngắn hạn (phiên)</div>
          <div className="text-white/50 text-sm">
            “Phiên” = ngày có công bố dữ liệu. Δ7/Δ14 = so với 7/14 phiên trước.
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px]">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Kỳ</th>
                  <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Mới nhất</th>
                  <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Δ7</th>
                  <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Δ14</th>
                </tr>
              </thead>
              <tbody>
                {signalRows.map((r) => (
                  <tr key={r.tenor} className="border-b border-white/5 hover:bg-white/5">
                    <td className="py-2 px-3 text-white">{r.tenor}</td>
                    <td className="py-2 px-3 text-right text-white/90">
                      {fmtPct(r.latestRate)}
                      <span className="text-white/40 text-xs">{" "}({r.source || "—"})</span>
                    </td>
                    <td className="py-2 px-3 text-right text-white/90 font-semibold">{fmtBps(r.d7_bps)}</td>
                    <td className="py-2 px-3 text-right text-white/90 font-semibold">{fmtBps(r.d14_bps)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-white/50 text-xs">
            {loadingSignals ? "Đang cập nhật…" : `As of: ${fmtShortDate(compare?.today_date)}`}
          </div>
        </GlassCard>

        <GlassCard className="space-y-2">
          <div className="text-white font-semibold">Độ phủ (phiên)</div>
          <div className="text-white/50 text-sm">
            Nếu “hôm qua” trống hoặc 2W/9M thiếu: thường là do nguồn không công bố đủ, không phải lỗi hệ thống.
          </div>
          <div className="space-y-2 text-sm">
            {signalRows.map((r) => (
              <div key={r.tenor} className="flex items-center justify-between gap-3">
                <div className="text-white/70">{r.tenor}</div>
                <div className="text-white/80">
                  {r.n} điểm • {r.pairs14}/{20} cặp (Δ14)
                </div>
              </div>
            ))}
          </div>
        </GlassCard>

        <GlassCard className="space-y-2">
          <div className="text-white font-semibold">Giải thích nhanh</div>
          <div className="text-white/60 text-sm space-y-2">
            <div>- “Δ” = chênh lệch so với phiên trước (bps).</div>
            <div>- “Δ7/Δ14” = chênh lệch so với 7/14 phiên trước.</div>
            <div>- Đây là mô tả dữ liệu, không phải khuyến nghị tài chính.</div>
          </div>
        </GlassCard>
      </div>

      <details className="glass-card rounded-2xl p-6">
        <summary className="cursor-pointer text-white font-semibold select-none">Nâng cao: Chuỗi thời gian</summary>
        <div className="mt-4 space-y-3">
          <div className="flex items-end justify-between gap-4 flex-wrap">
            <div className="text-white/50 text-sm">Chọn kỳ và khoảng thời gian để xem xu hướng.</div>
            <div className="flex items-center gap-2 flex-wrap">
              <select
                value={tenor}
                onChange={(e) => setTenor(e.target.value)}
                className="glass-input px-4 py-2 rounded-lg text-white text-sm"
              >
                {tenors.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="glass-input px-4 py-2 rounded-lg text-white text-sm"
              />
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="glass-input px-4 py-2 rounded-lg text-white text-sm"
              />
              <button
                className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
                disabled={!startDate || !endDate || loadingSeries}
                onClick={() => loadSeries()}
              >
                {loadingSeries ? "Đang tải..." : "Xem"}
              </button>
            </div>
          </div>

          {errorSeries && <div className="text-red-300 text-sm">{errorSeries}</div>}

          <ResponsiveContainer width="100%" height={360}>
            <LineChart data={seriesChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="date" stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} />
              <YAxis
                stroke="rgba(255,255,255,0.6)"
                style={{ fontSize: "12px" }}
                tickFormatter={(v) => `${Number(v).toFixed(2)}%`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "rgba(15, 23, 42, 0.9)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: "12px",
                }}
                labelStyle={{ color: "rgba(255,255,255,0.8)" }}
                formatter={(value: any, _name: any, props: any) => {
                  const src = props?.payload?.source ? ` (${props.payload.source})` : "";
                  return [`${fmtPct(value)}${src}`, "Rate"];
                }}
              />
              <Line type="monotone" dataKey="rate" stroke="#3b82f6" strokeWidth={2} dot={false} activeDot={{ r: 5 }} />
            </LineChart>
          </ResponsiveContainer>

          <div className="text-white/50 text-sm">
            Điểm dữ liệu: <span className="text-white/70">{series.length}</span>
          </div>
        </div>
      </details>
    </div>
  );
}
