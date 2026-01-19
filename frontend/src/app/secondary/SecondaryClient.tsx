"use client";

import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import { bondlabApi, SecondaryTradingRecord } from "@/lib/bondlabApi";
import {
  Area,
  AreaChart,
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

function fmtDate(value?: string | null) {
  if (!value) return "—";
  return value;
}

function daysBetween(start: string, end: string) {
  const a = new Date(start).getTime();
  const b = new Date(end).getTime();
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  const diff = Math.floor((b - a) / (24 * 3600 * 1000));
  return diff >= 0 ? diff : null;
}

function summarizeByDate(rows: SecondaryTradingRecord[]) {
  const by: Record<string, { date: string; volume: number; value: number }> = {};
  for (const r of rows) {
    const d = r.date;
    if (!by[d]) by[d] = { date: d, volume: 0, value: 0 };
    if (r.volume != null) by[d].volume += r.volume;
    if (r.value != null) by[d].value += r.value;
  }
  return Object.values(by).sort((a, b) => a.date.localeCompare(b.date));
}

export function SecondaryClient({
  initialRows,
  initialEndDate,
}: {
  initialRows: SecondaryTradingRecord[];
  initialEndDate: string;
}) {
  const [rows, setRows] = useState<SecondaryTradingRecord[]>(initialRows);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [endDate, setEndDate] = useState<string>(initialEndDate);
  const [startDate, setStartDate] = useState<string>(initialEndDate ? addDays(initialEndDate, -90) : "");
  const [segment, setSegment] = useState<string>("");
  const [bucket, setBucket] = useState<string>("");

  useEffect(() => {
    setRows(initialRows);
    setEndDate(initialEndDate);
    if (initialEndDate) setStartDate(addDays(initialEndDate, -90));
  }, [initialRows, initialEndDate]);

  const segmentOptions = useMemo(() => {
    const s = new Set<string>();
    for (const r of initialRows) s.add(r.segment);
    return Array.from(s).sort();
  }, [initialRows]);

  const bucketOptions = useMemo(() => {
    const s = new Set<string>();
    for (const r of initialRows) s.add(r.bucket_label);
    return Array.from(s).sort();
  }, [initialRows]);

  const chartData = useMemo(() => summarizeByDate(rows), [rows]);

  const latestDay = useMemo(() => (chartData.length ? chartData[chartData.length - 1] : null), [chartData]);
  const prevDay = useMemo(() => (chartData.length >= 2 ? chartData[chartData.length - 2] : null), [chartData]);
  const valueDelta = useMemo(
    () => (latestDay && prevDay ? latestDay.value - prevDay.value : null),
    [latestDay, prevDay]
  );
  const volumeDelta = useMemo(
    () => (latestDay && prevDay ? latestDay.volume - prevDay.volume : null),
    [latestDay, prevDay]
  );

  const valueDelta14 = useMemo(() => {
    if (chartData.length <= 14) return null;
    const now = chartData[chartData.length - 1]?.value;
    const prev = chartData[chartData.length - 1 - 14]?.value;
    if (now == null || prev == null) return null;
    return now - prev;
  }, [chartData]);

  const topBuckets = useMemo(() => {
    const lastDates = chartData.slice(Math.max(0, chartData.length - 30)).map((d) => d.date);
    const dateSet = new Set(lastDates);
    const byBucket: Record<string, number> = {};
    for (const r of rows) {
      if (!dateSet.has(r.date)) continue;
      if (r.value == null) continue;
      byBucket[r.bucket_label] = (byBucket[r.bucket_label] || 0) + r.value;
    }
    return Object.entries(byBucket)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([bucket_label, value]) => ({ bucket_label, value }));
  }, [rows, chartData]);

  async function load() {
    if (!startDate || !endDate) return;
    try {
      setLoading(true);
      setError(null);
      const data = await bondlabApi.secondaryRange({
        start_date: startDate,
        end_date: endDate,
        segment: segment || undefined,
        bucket: bucket || undefined,
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
    return `/api/export/secondary.csv?${sp.toString()}`;
  }, [startDate, endDate]);

  const totals = useMemo(() => {
    let volume = 0;
    let value = 0;
    for (const r of rows) {
      if (r.volume != null) volume += r.volume;
      if (r.value != null) value += r.value;
    }
    return { volume, value };
  }, [rows]);

  const coverageInfo = useMemo(() => {
    if (!startDate || !endDate) return null;
    const span = daysBetween(startDate, endDate);
    return {
      obs: chartData.length,
      span_days: span,
    };
  }, [startDate, endDate, chartData.length]);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Secondary</h1>
          <p className="text-white/60 mt-2">Thống kê giao dịch thứ cấp TPCP (HNX).</p>
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
            value={segment}
            onChange={(e) => setSegment(e.target.value)}
            className="glass-input px-4 py-2 rounded-lg text-white text-sm"
          >
            <option value="">Tất cả segment</option>
            {segmentOptions.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
          <select
            value={bucket}
            onChange={(e) => setBucket(e.target.value)}
            className="glass-input px-4 py-2 rounded-lg text-white text-sm"
          >
            <option value="">Tất cả bucket</option>
            {bucketOptions.map((x) => (
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
            <a className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" href={exportUrl}>
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

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Phiên gần nhất</div>
          <div className="text-white text-xl font-bold">{latestDay?.date || "—"}</div>
          <div className="text-white/60 text-sm">
            Giá trị: <span className="text-white/80 font-semibold">{latestDay ? fmtNumber(latestDay.value) : "—"}</span>
          </div>
          <div className="text-white/60 text-sm">
            Δ so phiên trước: <span className="text-white/80 font-semibold">{valueDelta == null ? "—" : fmtNumber(valueDelta)}</span>
          </div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Khối lượng</div>
          <div className="text-white text-xl font-bold">{latestDay ? fmtNumber(latestDay.volume) : "—"}</div>
          <div className="text-white/60 text-sm">
            Δ so phiên trước: <span className="text-white/80 font-semibold">{volumeDelta == null ? "—" : fmtNumber(volumeDelta)}</span>
          </div>
          <div className="text-white/40 text-sm">Đây là mô tả điều kiện thị trường, không phải khuyến nghị.</div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Tín hiệu (14 phiên)</div>
          <div className="text-white text-xl font-bold">{valueDelta14 == null ? "—" : fmtNumber(valueDelta14)}</div>
          <div className="text-white/40 text-sm">Thay đổi giá trị giao dịch so với 14 phiên trước (phiên = ngày có dữ liệu).</div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Độ phủ</div>
          <div className="text-white text-xl font-bold">{coverageInfo ? `${coverageInfo.obs} phiên` : "—"}</div>
          <div className="text-white/60 text-sm">
            {fmtDate(startDate)} → {fmtDate(endDate)}
            {coverageInfo?.span_days != null ? <span className="text-white/50"> • {coverageInfo.span_days + 1} ngày</span> : null}
          </div>
          <div className="text-white/40 text-sm">Secondary thường có ngày thiếu dữ liệu (không phải lỗi).</div>
        </GlassCard>
      </div>

      <GlassCard>
        <div className="flex items-start justify-between gap-4 flex-wrap mb-3">
          <div>
            <div className="text-white font-semibold">Top buckets (30 phiên gần nhất)</div>
            <div className="text-white/50 text-sm">Tổng giá trị theo bucket (top 6).</div>
          </div>
        </div>
        {topBuckets.length === 0 ? (
          <div className="text-white/60 text-sm">Chưa đủ dữ liệu để tổng hợp.</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {topBuckets.map((b) => (
              <div key={b.bucket_label} className="flex items-center justify-between gap-3 border border-white/10 rounded-xl px-3 py-2">
                <div className="text-white/80">{b.bucket_label}</div>
                <div className="text-white font-semibold">{fmtNumber(b.value)}</div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      <details className="glass-card rounded-2xl p-6">
        <summary className="cursor-pointer text-white font-semibold select-none">Chi tiết (biểu đồ & dữ liệu)</summary>
        <div className="mt-4 space-y-6">
          <div>
            <div className="text-white font-semibold mb-3">Tổng hợp theo ngày</div>
            <ResponsiveContainer width="100%" height={360}>
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="date" stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} />
                <YAxis
                  stroke="rgba(255,255,255,0.6)"
                  style={{ fontSize: "12px" }}
                  tickFormatter={(v) => Intl.NumberFormat("vi-VN", { notation: "compact" }).format(Number(v))}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "rgba(15, 23, 42, 0.9)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: "12px",
                  }}
                  labelStyle={{ color: "rgba(255,255,255,0.8)" }}
                  formatter={(value: any, name: any) => [
                    fmtNumber(Number(value)),
                    name === "value" ? "Giá trị" : "Khối lượng",
                  ]}
                />
                <Legend />
                <Area type="monotone" dataKey="value" name="Giá trị" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.25} />
                <Area type="monotone" dataKey="volume" name="Khối lượng" stroke="#22c55e" fill="#22c55e" fillOpacity={0.18} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div>
            <div className="text-white font-semibold mb-3">Bảng dữ liệu</div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px]">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Ngày</th>
                    <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Segment</th>
                    <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Bucket</th>
                    <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Volume</th>
                    <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Value</th>
                    <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Avg yield</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, idx) => (
                    <tr key={`${r.date}-${r.segment}-${r.bucket_label}-${idx}`} className="border-b border-white/5 hover:bg-white/5">
                      <td className="py-2 px-3 text-white">{r.date}</td>
                      <td className="py-2 px-3 text-white/80">{r.segment}</td>
                      <td className="py-2 px-3 text-white/80">{r.bucket_label}</td>
                      <td className="py-2 px-3 text-right text-white/90">{fmtNumber(r.volume)}</td>
                      <td className="py-2 px-3 text-right text-white/90">{fmtNumber(r.value)}</td>
                      <td className="py-2 px-3 text-right text-white/90">{r.avg_yield == null ? "—" : `${r.avg_yield.toFixed(2)}%`}</td>
                    </tr>
                  ))}
                  {rows.length === 0 ? (
                    <tr>
                      <td className="py-6 px-3 text-white/60" colSpan={6}>
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
