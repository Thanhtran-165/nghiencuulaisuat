"use client";

import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import { bondlabApi, AuctionRecord } from "@/lib/bondlabApi";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

function addDays(dateStr: string, deltaDays: number) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + deltaDays);
  return isoDate(d);
}

function fmtNumber(value?: number | null) {
  if (value == null) return "—";
  return Intl.NumberFormat("vi-VN").format(value);
}

function fmtPct(value?: number | null) {
  if (value == null) return "—";
  return `${value.toFixed(2)}%`;
}

function fmtDate(value?: string | null) {
  if (!value) return "—";
  return value;
}

function summarizeByDate(rows: AuctionRecord[]) {
  const by: Record<string, { date: string; offered: number; sold: number; btcVals: number[] }> = {};
  for (const r of rows) {
    const d = r.date;
    if (!by[d]) by[d] = { date: d, offered: 0, sold: 0, btcVals: [] };
    if (r.amount_offered != null) by[d].offered += r.amount_offered;
    if (r.amount_sold != null) by[d].sold += r.amount_sold;
    if (r.bid_to_cover != null) by[d].btcVals.push(r.bid_to_cover);
  }
  const out = Object.values(by)
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((x) => ({
      date: x.date,
      offered: x.offered,
      sold: x.sold,
      sold_ratio: x.offered > 0 ? x.sold / x.offered : null,
      btc:
        x.btcVals.length === 0
          ? null
          : x.btcVals.sort((a, b) => a - b)[Math.floor((x.btcVals.length - 1) * 0.5)],
    }));
  return out;
}

function median(values: Array<number | null | undefined>) {
  const xs = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v)).sort((a, b) => a - b);
  if (xs.length === 0) return null;
  return xs[Math.floor((xs.length - 1) * 0.5)];
}

function fmtPctRatio(value?: number | null) {
  if (value == null) return "—";
  return `${(value * 100).toFixed(0)}%`;
}

export function AuctionsClient({ initialRows, initialEndDate }: { initialRows: AuctionRecord[]; initialEndDate: string }) {
  const [rows, setRows] = useState<AuctionRecord[]>(initialRows);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [endDate, setEndDate] = useState<string>(initialEndDate);
  const [startDate, setStartDate] = useState<string>(initialEndDate ? addDays(initialEndDate, -90) : "");
  const [instrumentType, setInstrumentType] = useState<string>("");
  const [tenor, setTenor] = useState<string>("");

  useEffect(() => {
    setRows(initialRows);
    setEndDate(initialEndDate);
    if (initialEndDate) setStartDate(addDays(initialEndDate, -90));
  }, [initialRows, initialEndDate]);

  const instrumentOptions = useMemo(() => {
    const s = new Set<string>();
    for (const r of initialRows) s.add(r.instrument_type);
    return Array.from(s).sort();
  }, [initialRows]);

  const tenorOptions = useMemo(() => {
    const s = new Set<string>();
    for (const r of initialRows) s.add(r.tenor_label);
    return Array.from(s).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  }, [initialRows]);

  const chartData = useMemo(() => summarizeByDate(rows), [rows]);

  const latestDay = useMemo(() => (chartData.length ? chartData[chartData.length - 1] : null), [chartData]);
  const prevDay = useMemo(() => (chartData.length >= 2 ? chartData[chartData.length - 2] : null), [chartData]);

  const baseline = useMemo(() => {
    const window = chartData.slice(Math.max(0, chartData.length - 20), Math.max(0, chartData.length - 1));
    return {
      btc_med: median(window.map((x) => x.btc)),
      sold_ratio_med: median(window.map((x) => x.sold_ratio)),
      offered_med: median(window.map((x) => x.offered)),
      sold_med: median(window.map((x) => x.sold)),
      n: window.length,
    };
  }, [chartData]);

  const shortTrend = useMemo(() => {
    const a = chartData.slice(Math.max(0, chartData.length - 3));
    const b = chartData.slice(Math.max(0, chartData.length - 6), Math.max(0, chartData.length - 3));
    return {
      btc_recent: median(a.map((x) => x.btc)),
      btc_prev: median(b.map((x) => x.btc)),
      sold_ratio_recent: median(a.map((x) => x.sold_ratio)),
      sold_ratio_prev: median(b.map((x) => x.sold_ratio)),
    };
  }, [chartData]);

  async function load() {
    if (!startDate || !endDate) return;
    try {
      setLoading(true);
      setError(null);
      const data = await bondlabApi.auctionsRange({
        start_date: startDate,
        end_date: endDate,
        instrument_type: instrumentType || undefined,
        tenor: tenor || undefined,
      });
      setRows(data);
    } catch (e: any) {
      setError(e?.message || "Không thể tải dữ liệu");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }

  const exportUrl = useMemo(() => {
    if (!startDate || !endDate) return null;
    const sp = new URLSearchParams({ start_date: startDate, end_date: endDate });
    return `/api/export/auctions.csv?${sp.toString()}`;
  }, [startDate, endDate]);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Auctions</h1>
          <p className="text-white/60 mt-2">Kết quả đấu thầu TPCP (HNX).</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
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
          <select
            value={instrumentType}
            onChange={(e) => setInstrumentType(e.target.value)}
            className="glass-input px-4 py-2 rounded-lg text-white text-sm"
          >
            <option value="">Tất cả loại</option>
            {instrumentOptions.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
          <select
            value={tenor}
            onChange={(e) => setTenor(e.target.value)}
            className="glass-input px-4 py-2 rounded-lg text-white text-sm"
          >
            <option value="">Tất cả kỳ hạn</option>
            {tenorOptions.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
          <button
            className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
            disabled={loading || !startDate || !endDate}
            onClick={() => load()}
          >
            {loading ? "Đang tải..." : "Xem"}
          </button>
          {exportUrl && (
            <a
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10"
              href={exportUrl}
            >
              Tải CSV
            </a>
          )}
        </div>
      </div>

      {error && (
        <GlassCard>
          <div className="text-red-300 font-semibold mb-1">Lỗi</div>
          <div className="text-white/60 text-sm">{error}</div>
        </GlassCard>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Phiên gần nhất</div>
          <div className="text-white text-xl font-bold">{latestDay?.date || "—"}</div>
          <div className="text-white/60 text-sm">
            Tỷ lệ bán: <span className="text-white/80 font-semibold">{fmtPctRatio(latestDay?.sold_ratio ?? null)}</span>
            {prevDay?.sold_ratio != null && latestDay?.sold_ratio != null ? (
              <span className="text-white/50"> • so với phiên trước: {fmtPctRatio(latestDay.sold_ratio - prevDay.sold_ratio)}</span>
            ) : null}
          </div>
          <div className="text-white/40 text-sm">Đây là mô tả điều kiện đấu thầu, không phải khuyến nghị.</div>
        </GlassCard>

        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Cầu đấu thầu (BTC median)</div>
          <div className="text-white text-xl font-bold">
            {latestDay?.btc == null ? "—" : latestDay.btc.toFixed(2)}
          </div>
          <div className="text-white/60 text-sm">
            Mốc tham chiếu (20 phiên):{" "}
            <span className="text-white/80 font-semibold">{baseline.btc_med == null ? "—" : baseline.btc_med.toFixed(2)}</span>
            <span className="text-white/50"> • n={baseline.n}</span>
          </div>
          <div className="text-white/40 text-sm">BTC cao hơn thường phản ánh nhu cầu mạnh hơn (tương đối).</div>
        </GlassCard>

        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Tín hiệu ngắn (3 phiên)</div>
          <div className="text-white/60 text-sm">
            BTC:{" "}
            <span className="text-white/80 font-semibold">
              {shortTrend.btc_recent == null ? "—" : shortTrend.btc_recent.toFixed(2)}
            </span>{" "}
            vs{" "}
            <span className="text-white/60">{shortTrend.btc_prev == null ? "—" : shortTrend.btc_prev.toFixed(2)}</span>
          </div>
          <div className="text-white/60 text-sm">
            Tỷ lệ bán:{" "}
            <span className="text-white/80 font-semibold">{fmtPctRatio(shortTrend.sold_ratio_recent)}</span>{" "}
            vs <span className="text-white/60">{fmtPctRatio(shortTrend.sold_ratio_prev)}</span>
          </div>
          <div className="text-white/40 text-sm">Auctions không diễn ra hàng ngày, nên dùng “phiên” (observations).</div>
        </GlassCard>
      </div>

      <details className="glass-card rounded-2xl p-6">
        <summary className="cursor-pointer text-white font-semibold select-none">Chi tiết (biểu đồ & dữ liệu)</summary>
        <div className="mt-4 space-y-6">
          <div>
            <div className="text-white font-semibold">Tổng hợp theo ngày</div>
            <div className="text-white/50 text-sm mb-3">
              {fmtDate(startDate)} → {fmtDate(endDate)} • {rows.length} dòng • {chartData.length} phiên
            </div>

            <ResponsiveContainer width="100%" height={360}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="date" stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} />
                <YAxis
                  yAxisId="left"
                  stroke="rgba(255,255,255,0.6)"
                  style={{ fontSize: "12px" }}
                  tickFormatter={(v) => Intl.NumberFormat("vi-VN", { notation: "compact" }).format(Number(v))}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="rgba(255,255,255,0.6)"
                  style={{ fontSize: "12px" }}
                  tickFormatter={(v) => Number(v).toFixed(1)}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "rgba(15, 23, 42, 0.9)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: "12px",
                  }}
                  labelStyle={{ color: "rgba(255,255,255,0.8)" }}
                  formatter={(value: any, name: any) => {
                    if (name === "btc") return [value == null ? "—" : Number(value).toFixed(2), "BTC (median)"];
                    if (name === "sold_ratio") return [value == null ? "—" : `${(Number(value) * 100).toFixed(0)}%`, "Tỷ lệ bán"];
                    return [fmtNumber(Number(value)), name === "offered" ? "Chào thầu" : "Bán"];
                  }}
                />
                <Legend />
                <Bar yAxisId="left" dataKey="offered" name="Chào thầu" fill="#60a5fa" fillOpacity={0.45} />
                <Bar yAxisId="left" dataKey="sold" name="Bán" fill="#22c55e" fillOpacity={0.45} />
                <Bar yAxisId="right" dataKey="btc" name="BTC (median)" fill="#f59e0b" fillOpacity={0.35} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div>
            <div className="text-white font-semibold mb-3">Bảng dữ liệu</div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px]">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Ngày</th>
                    <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Loại</th>
                    <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Kỳ</th>
                    <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Chào thầu</th>
                    <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Bán</th>
                    <th className="text-right py-2 px-3 text-sm font-medium text-white/60">BTC</th>
                    <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Cut-off</th>
                    <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Avg</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, idx) => (
                    <tr
                      key={`${r.date}-${r.instrument_type}-${r.tenor_label}-${idx}`}
                      className="border-b border-white/5 hover:bg-white/5"
                    >
                      <td className="py-2 px-3 text-white">{r.date}</td>
                      <td className="py-2 px-3 text-white/80">{r.instrument_type}</td>
                      <td className="py-2 px-3 text-white/80">{r.tenor_label}</td>
                      <td className="py-2 px-3 text-right text-white/90">{fmtNumber(r.amount_offered)}</td>
                      <td className="py-2 px-3 text-right text-white/90">{fmtNumber(r.amount_sold)}</td>
                      <td className="py-2 px-3 text-right text-white/90 font-semibold">
                        {r.bid_to_cover == null ? "—" : r.bid_to_cover.toFixed(2)}
                      </td>
                      <td className="py-2 px-3 text-right text-white/90">{fmtPct(r.cut_off_yield)}</td>
                      <td className="py-2 px-3 text-right text-white/90">{fmtPct(r.avg_yield)}</td>
                    </tr>
                  ))}
                  {rows.length === 0 ? (
                    <tr>
                      <td className="py-6 px-3 text-white/60" colSpan={8}>
                        Không có dữ liệu cho khoảng này.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </details>
    </div>
  );
}
