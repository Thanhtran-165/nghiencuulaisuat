"use client";

import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import { bondlabApi, YieldCurveMetricsRecord, YieldCurveRecord } from "@/lib/bondlabApi";
import {
  CartesianGrid,
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

function fmtBpsFromPctDiff(value?: number | null) {
  if (value == null) return "—";
  return `${(value * 100).toFixed(0)} bps`;
}

function fmtSignedBpsFromPctDiff(value?: number | null) {
  if (value == null) return "—";
  const bps = value * 100;
  const sign = bps > 0 ? "+" : "";
  return `${sign}${bps.toFixed(0)} bps`;
}

function fmtShortDate(iso?: string | null) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

function normalize(records: YieldCurveRecord[]) {
  return [...records].sort((a, b) => a.tenor_days - b.tenor_days);
}

function pickYield(r: YieldCurveRecord) {
  // Prefer annual spot; fallback to par_yield
  if (r.spot_rate_annual != null) return r.spot_rate_annual;
  if (r.par_yield != null) return r.par_yield;
  return null;
}

export function YieldCurveClient({
  initialDate,
  initialData,
}: {
  initialDate: string;
  initialData: YieldCurveRecord[];
}) {
  const [date, setDate] = useState(initialDate);
  const [data, setData] = useState<YieldCurveRecord[]>(initialData);
  const [metrics, setMetrics] = useState<YieldCurveMetricsRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDate(initialDate);
    setData(initialData);
  }, [initialDate, initialData]);

  useEffect(() => {
    let cancelled = false;
    bondlabApi
      .yieldCurveMetrics({ end_date: initialDate, lookback: 180 })
      .then((rows) => {
        if (!cancelled) setMetrics(rows);
      })
      .catch(() => {
        if (!cancelled) setMetrics([]);
      });
    return () => {
      cancelled = true;
    };
  }, [initialDate]);

  const chartData = useMemo(() => {
    return normalize(data).map((r) => ({
      tenor_label: r.tenor_label,
      y: pickYield(r),
      source: r.source,
      tenor_days: r.tenor_days,
    }));
  }, [data]);

  const twoY = useMemo(() => {
    const r = data.find((x) => x.tenor_label === "2Y");
    return r ? pickYield(r) : null;
  }, [data]);
  const fiveY = useMemo(() => {
    const r = data.find((x) => x.tenor_label === "5Y");
    return r ? pickYield(r) : null;
  }, [data]);
  const tenY = useMemo(() => {
    const r = data.find((x) => x.tenor_label === "10Y");
    return r ? pickYield(r) : null;
  }, [data]);
  const spread = useMemo(() => (tenY != null && twoY != null ? tenY - twoY : null), [tenY, twoY]);

  const latestMetrics = useMemo(() => (metrics.length ? metrics[metrics.length - 1] : null), [metrics]);
  const slope = latestMetrics?.slope_10y_2y ?? null;
  const curvature = latestMetrics?.curvature_2_5_10 ?? null;

  function deltaFromBack<T extends keyof YieldCurveMetricsRecord>(key: T, back: number) {
    if (metrics.length < back + 1) return null;
    const now = metrics[metrics.length - 1]?.[key] as any;
    const prev = metrics[metrics.length - 1 - back]?.[key] as any;
    if (now == null || prev == null) return null;
    return Number(now) - Number(prev);
  }

  const slopeDelta14 = useMemo(() => deltaFromBack("slope_10y_2y", 14), [metrics]);
  const curvatureDelta14 = useMemo(() => deltaFromBack("curvature_2_5_10", 14), [metrics]);

  const metricsChartData = useMemo(() => {
    return metrics.map((m) => ({
      date: m.date,
      slope_bps: m.slope_10y_2y == null ? null : m.slope_10y_2y * 100,
      curvature_bps: m.curvature_2_5_10 == null ? null : m.curvature_2_5_10 * 100,
    }));
  }, [metrics]);

  async function load(d: string) {
    try {
      setLoading(true);
      setError(null);
      const [rows, metricRows] = await Promise.all([
        bondlabApi.yieldCurveByDate(d),
        bondlabApi.yieldCurveMetrics({ end_date: d, lookback: 180 }),
      ]);
      setData(rows);
      setMetrics(metricRows);
    } catch (e: any) {
      setError(e?.message || "Không thể tải dữ liệu");
      setData([]);
      setMetrics([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Yield Curve</h1>
          <p className="text-white/60 mt-2">
            Đường cong lợi suất TPCP theo kỳ hạn (nguồn HNX). Phần “Insights” tập trung vào cấu trúc: mức (level), độ dốc (slope), độ lồi (curvature).
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="text-white/60 text-sm">Ngày</div>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="glass-input px-4 py-2 rounded-lg text-white text-sm"
          />
          <button
            className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
            disabled={!date || loading}
            onClick={() => load(date)}
          >
            {loading ? "Đang tải..." : "Xem"}
          </button>
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
          <div className="text-white/60 text-sm">2Y</div>
          <div className="text-white text-2xl font-bold">{fmtPct(twoY)}</div>
          <div className="text-white/40 text-sm">Kỳ 2 năm</div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">5Y</div>
          <div className="text-white text-2xl font-bold">{fmtPct(fiveY)}</div>
          <div className="text-white/40 text-sm">Kỳ 5 năm</div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">10Y</div>
          <div className="text-white text-2xl font-bold">{fmtPct(tenY)}</div>
          <div className="text-white/60 text-sm">
            Spread 10Y–2Y: <span className="text-white/80 font-semibold">{fmtBpsFromPctDiff(spread)}</span>
          </div>
        </GlassCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Level (10Y)</div>
          <div className="text-white text-xl font-bold">{fmtPct(latestMetrics?.y10 ?? tenY)}</div>
          <div className="text-white/40 text-sm">Mặt bằng lợi suất dài hạn (đại diện).</div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Slope (10Y–2Y)</div>
          <div className="text-white text-xl font-bold">{fmtBpsFromPctDiff(slope)}</div>
          <div className="text-white/60 text-sm">
            So với 14 phiên: <span className="text-white/80 font-semibold">{fmtSignedBpsFromPctDiff(slopeDelta14)}</span>
          </div>
          <div className="text-white/40 text-sm">Độ dốc đường cong (dài–ngắn).</div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Curvature (2*5Y − 2Y − 10Y)</div>
          <div className="text-white text-xl font-bold">{fmtBpsFromPctDiff(curvature)}</div>
          <div className="text-white/60 text-sm">
            So với 14 phiên:{" "}
            <span className="text-white/80 font-semibold">{fmtSignedBpsFromPctDiff(curvatureDelta14)}</span>
          </div>
          <div className="text-white/40 text-sm">Độ lồi ở “bụng” (5Y) so với 2Y & 10Y.</div>
        </GlassCard>
      </div>

      <GlassCard>
        <div className="flex items-start justify-between gap-4 flex-wrap mb-4">
          <div>
            <div className="text-white font-semibold">Curve insights (time series)</div>
            <div className="text-white/50 text-sm">
              Window: 180 phiên{" "}
              {latestMetrics?.date ? (
                <>
                  {" • "}As of: <span className="text-white/70">{fmtShortDate(latestMetrics.date)}</span>
                </>
              ) : null}
              {" • "}
              Điểm dữ liệu: <span className="text-white/70">{metrics.length}</span>
            </div>
          </div>
        </div>

        {metrics.length === 0 ? (
          <div className="text-white/60 text-sm">Chưa có dữ liệu metrics trong khoảng chọn.</div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="h-[280px]">
              <div className="text-white/70 text-sm mb-2">Slope (10Y–2Y, bps)</div>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={metricsChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="date" hide />
                  <YAxis stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "rgba(15, 23, 42, 0.9)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: "12px",
                    }}
                    labelStyle={{ color: "rgba(255,255,255,0.8)" }}
                    formatter={(value: any) => [`${Number(value).toFixed(0)} bps`, "Slope"]}
                    labelFormatter={(label: any) => `Ngày ${fmtShortDate(String(label))}`}
                  />
                  <Line type="monotone" dataKey="slope_bps" stroke="#22c55e" strokeWidth={2} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="h-[280px]">
              <div className="text-white/70 text-sm mb-2">Curvature (bps)</div>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={metricsChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="date" hide />
                  <YAxis stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "rgba(15, 23, 42, 0.9)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: "12px",
                    }}
                    labelStyle={{ color: "rgba(255,255,255,0.8)" }}
                    formatter={(value: any) => [`${Number(value).toFixed(0)} bps`, "Curvature"]}
                    labelFormatter={(label: any) => `Ngày ${fmtShortDate(String(label))}`}
                  />
                  <Line type="monotone" dataKey="curvature_bps" stroke="#f59e0b" strokeWidth={2} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </GlassCard>

      <GlassCard>
        <div className="flex items-start justify-between gap-4 flex-wrap mb-4">
          <div>
            <div className="text-white font-semibold">Biểu đồ</div>
            <div className="text-white/50 text-sm">
              Ngày: <span className="text-white/70">{date || "—"}</span>
              {" • "}
              Điểm dữ liệu: <span className="text-white/70">{data.length}</span>
            </div>
          </div>
        </div>

        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis
              dataKey="tenor_label"
              stroke="rgba(255,255,255,0.6)"
              style={{ fontSize: "12px" }}
            />
            <YAxis
              stroke="rgba(255,255,255,0.6)"
              style={{ fontSize: "12px" }}
              domain={["dataMin - 0.1", "dataMax + 0.1"]}
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
                const v = value == null ? "—" : `${Number(value).toFixed(2)}%`;
                const src = props?.payload?.source ? ` (${props.payload.source})` : "";
                return [`${v}${src}`, "Yield"];
              }}
              labelFormatter={(_label: any, payload: any) => {
                const p = payload?.[0]?.payload;
                return p?.tenor_label ? `Kỳ ${p.tenor_label}` : "Kỳ hạn";
              }}
            />
            <Line
              type="monotone"
              dataKey="y"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={{ fill: "#3b82f6", strokeWidth: 2, r: 4 }}
              activeDot={{ r: 6 }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </GlassCard>

      <GlassCard>
        <div className="text-white font-semibold mb-3">Bảng dữ liệu</div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px]">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Kỳ</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Yield</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Nguồn</th>
              </tr>
            </thead>
            <tbody>
              {normalize(data).map((r) => (
                <tr key={`${r.tenor_label}-${r.tenor_days}`} className="border-b border-white/5 hover:bg-white/5">
                  <td className="py-2 px-3 text-white">{r.tenor_label}</td>
                  <td className="py-2 px-3 text-right text-white/90 font-semibold">{fmtPct(pickYield(r))}</td>
                  <td className="py-2 px-3 text-white/60">{r.source}</td>
                </tr>
              ))}
              {data.length === 0 ? (
                <tr>
                  <td className="py-6 px-3 text-white/60" colSpan={3}>
                    Không có dữ liệu cho ngày này.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}
