"use client";

import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import { bondlabApi, PolicyRateRecord } from "@/lib/bondlabApi";
import {
  CartesianGrid,
  Line,
  LineChart,
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

function fmtPct(value?: number | null) {
  if (value == null) return "—";
  return `${value.toFixed(2)}%`;
}

export function PolicyClient({ initialLatest }: { initialLatest: PolicyRateRecord[] }) {
  const latestDate = initialLatest[0]?.date || "";
  const rateNames = useMemo(() => {
    const s = new Set<string>();
    for (const r of initialLatest) s.add(r.rate_name);
    return Array.from(s).sort();
  }, [initialLatest]);

  const [selectedRate, setSelectedRate] = useState<string>(rateNames[0] || "");
  const [endDate, setEndDate] = useState<string>(latestDate);
  const [startDate, setStartDate] = useState<string>(latestDate ? addDays(latestDate, -365) : "");
  const [rows, setRows] = useState<PolicyRateRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSelectedRate((prev) => prev || rateNames[0] || "");
  }, [rateNames]);

  async function load() {
    if (!startDate || !endDate || !selectedRate) return;
    try {
      setLoading(true);
      setError(null);
      const data = await bondlabApi.policyRange({
        start_date: startDate,
        end_date: endDate,
        rate_name: selectedRate,
      });
      setRows(data);
    } catch (e: any) {
      setError(e?.message || "Không thể tải dữ liệu");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRate]);

  const chartData = useMemo(() => {
    return [...rows]
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((r) => ({ date: r.date, rate: r.rate, source: r.source }));
  }, [rows]);

  const exportUrl = useMemo(() => {
    if (!startDate || !endDate) return null;
    const sp = new URLSearchParams({ start_date: startDate, end_date: endDate });
    return `/api/export/policy-rates.csv?${sp.toString()}`;
  }, [startDate, endDate]);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Policy</h1>
          <p className="text-white/60 mt-2">Lãi suất điều hành (SBV).</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={selectedRate}
            onChange={(e) => setSelectedRate(e.target.value)}
            className="glass-input px-4 py-2 rounded-lg text-white text-sm"
          >
            {rateNames.map((x) => (
              <option key={x} value={x}>
                {x}
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
            disabled={loading || !selectedRate || !startDate || !endDate}
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {initialLatest.map((r) => (
          <GlassCard key={r.rate_name} className="space-y-2">
            <div className="text-white/60 text-sm">{r.rate_name}</div>
            <div className="text-white text-2xl font-bold">{fmtPct(r.rate)}</div>
            <div className="text-white/40 text-sm">
              Ngày: {r.date} • Nguồn: {r.source}
            </div>
          </GlassCard>
        ))}
      </div>

      <GlassCard>
        <div className="text-white font-semibold mb-3">Chuỗi thời gian: {selectedRate || "—"}</div>
        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={chartData}>
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
              formatter={(value: any) => fmtPct(value)}
            />
            <Line type="monotone" dataKey="rate" stroke="#3b82f6" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
        <div className="text-white/50 text-sm mt-2">Điểm dữ liệu: {rows.length}</div>
      </GlassCard>
    </div>
  );
}

