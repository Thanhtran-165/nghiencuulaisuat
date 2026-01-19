"use client";

import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import {
  bondlabApi,
  TransmissionAlertRecord,
  TransmissionCoverageSummary,
  TransmissionMetricRecord,
  TransmissionProgressSummary,
  TransmissionScoreSummary,
} from "@/lib/bondlabApi";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function alertTypeLabel(alertType: string) {
  switch (alertType) {
    case "ALERT_TRANSMISSION_TIGHTENING":
      return "Điều kiện truyền dẫn “thắt” bất thường";
    case "ALERT_TRANSMISSION_JUMP":
      return "Điểm truyền dẫn biến động mạnh";
    case "ALERT_LIQUIDITY_SPIKE":
      return "Liên ngân hàng O/N bất thường";
    case "ALERT_CURVE_BEAR_STEEPEN":
      return "Đường cong 10Y–2Y dốc lên";
    case "ALERT_AUCTION_WEAK":
      return "Đấu thầu yếu (BTC thấp)";
    case "ALERT_TURNOVER_DROP":
      return "Thanh khoản thứ cấp giảm";
    case "ALERT_POLICY_CHANGE":
      return "Thay đổi lãi suất điều hành";
    default:
      return alertType;
  }
}

function severityClass(severity?: string) {
  switch ((severity || "").toUpperCase()) {
    case "HIGH":
      return "text-red-300";
    case "MEDIUM":
      return "text-amber-200";
    case "LOW":
      return "text-emerald-200";
    default:
      return "text-white/80";
  }
}

function alertExplain(alertType: string) {
  switch (alertType) {
    case "ALERT_TRANSMISSION_TIGHTENING":
      return "Điểm Transmission hôm nay cao bất thường so với lịch sử gần đây (tính z-score trên chuỗi điểm theo ngày). Đây là tín hiệu thống kê, không khẳng định nguyên nhân.";
    case "ALERT_TRANSMISSION_JUMP":
      return "Điểm Transmission thay đổi mạnh so với phiên trước. Thường phản ánh biến động đồng thời ở nhiều thành phần (yield, liên ngân hàng, đấu thầu, thứ cấp, policy).";
    case "ALERT_LIQUIDITY_SPIKE":
      return "Lãi suất liên ngân hàng O/N tăng mạnh (theo z-score hoặc vượt ngưỡng tuyệt đối). Có thể là dấu hiệu căng thanh khoản ngắn hạn.";
    case "ALERT_CURVE_BEAR_STEEPEN":
      return "Độ dốc 10Y–2Y cao (hoặc tăng mạnh nếu có dữ liệu thay đổi). Thường gợi ý thị trường định giá mặt bằng dài hạn cao hơn tương đối so với ngắn hạn.";
    case "ALERT_AUCTION_WEAK":
      return "Nhu cầu đấu thầu yếu (bid-to-cover thấp). Có thể là dấu hiệu cầu sơ cấp giảm trong giai đoạn gần đây.";
    case "ALERT_TURNOVER_DROP":
      return "Thanh khoản thị trường thứ cấp giảm (z-score âm lớn). Có thể làm tín hiệu giá kém ổn định hơn.";
    case "ALERT_POLICY_CHANGE":
      return "Hệ thống phát hiện thay đổi ở lãi suất điều hành (refinancing/rediscount/base) so với kỳ trước.";
    case "ALERT_TRANSMISSION_HIGH":
      return "Điểm Transmission vượt ngưỡng tuyệt đối cấu hình. Đây là rule đơn giản, phụ thuộc ngưỡng trong Admin.";
    case "ALERT_STRESS_HIGH":
      return "BondY Stress Index vượt ngưỡng tuyệt đối cấu hình. Đây là rule đơn giản, phụ thuộc ngưỡng trong Admin.";
    default:
      return "Cảnh báo dựa trên rule thống kê/threshold. Xem “source_data” để biết chi tiết điều kiện kích hoạt.";
  }
}

function alertLink(alertType: string) {
  switch (alertType) {
    case "ALERT_LIQUIDITY_SPIKE":
      return { href: "/interbank", label: "Mở Interbank" };
    case "ALERT_CURVE_BEAR_STEEPEN":
    case "ALERT_TRANSMISSION_TIGHTENING":
    case "ALERT_TRANSMISSION_JUMP":
      return { href: "/yield-curve", label: "Mở Yield Curve" };
    case "ALERT_AUCTION_WEAK":
      return { href: "/auctions", label: "Mở Auctions" };
    case "ALERT_TURNOVER_DROP":
      return { href: "/secondary", label: "Mở Secondary" };
    case "ALERT_POLICY_CHANGE":
      return { href: "/policy", label: "Mở Policy" };
    default:
      return { href: "/transmission", label: "Mở Transmission" };
  }
}

function fmtPct(v?: number | null) {
  if (v == null) return "—";
  return `${v.toFixed(2)}%`;
}

function fmtScore(v?: number | null) {
  if (v == null) return "—";
  return v.toFixed(1);
}

function fmtBpsFromPct(v?: number | null) {
  if (v == null) return "—";
  return `${(v * 100).toFixed(0)} bps`;
}

function fmtBps(v?: number | null) {
  if (v == null) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(0)} bps`;
}

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

function addDays(dateStr: string, deltaDays: number) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + deltaDays);
  return isoDate(d);
}

async function postJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: "POST", cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function pickMetric(metrics: TransmissionMetricRecord[], name: string) {
  return metrics.find((m) => m.metric_name === name);
}

function fmtAlertValue(a: TransmissionAlertRecord) {
  if (a.metric_value == null) return "—";
  switch (a.alert_type) {
    case "ALERT_LIQUIDITY_SPIKE":
      // This alert can expose either absolute % level or z-score, depending on trigger_mode.
      try {
        const raw = (a as any).source_data;
        const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
        if (parsed?.trigger_mode === "zscore") {
          return `z=${a.metric_value.toFixed(2)}`;
        }
      } catch {
        // ignore parsing errors
      }
      return fmtPct(a.metric_value);
    case "ALERT_CURVE_BEAR_STEEPEN":
      return fmtBpsFromPct(a.metric_value);
    case "ALERT_TRANSMISSION_TIGHTENING":
      return fmtScore(a.metric_value);
    case "ALERT_TRANSMISSION_JUMP":
      return `${a.metric_value > 0 ? "+" : ""}${a.metric_value.toFixed(1)} pts`;
    case "ALERT_TURNOVER_DROP":
      return a.metric_value.toFixed(2);
    default:
      return a.metric_value.toFixed(2);
  }
}

function fmtAlertThreshold(a: TransmissionAlertRecord) {
  if (a.threshold == null) return "—";
  switch (a.alert_type) {
    case "ALERT_LIQUIDITY_SPIKE":
      try {
        const raw = (a as any).source_data;
        const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
        if (parsed?.trigger_mode === "zscore") {
          return `z≥${a.threshold.toFixed(2)}`;
        }
      } catch {
        // ignore parsing errors
      }
      return fmtPct(a.threshold);
    case "ALERT_CURVE_BEAR_STEEPEN":
      return fmtBpsFromPct(a.threshold);
    case "ALERT_TRANSMISSION_TIGHTENING":
      return fmtScore(a.threshold);
    case "ALERT_TRANSMISSION_JUMP":
      return `${a.threshold.toFixed(0)} pts`;
    case "ALERT_TURNOVER_DROP":
      return a.threshold.toFixed(2);
    default:
      return a.threshold.toFixed(2);
  }
}

function parseAlertSourceData(a: TransmissionAlertRecord): any | null {
  try {
    const raw = (a as any).source_data;
    return typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch {
    return null;
  }
}

function EvidenceSummary({ alert }: { alert: TransmissionAlertRecord }) {
  const parsed = parseAlertSourceData(alert);
  const ev = parsed?.evidence;
  if (!ev || typeof ev !== "object") return null;

  const rows: Array<{ k: string; v: string }> = [];
  if (typeof ev.metric === "string") rows.push({ k: "Metric", v: ev.metric });
  if (typeof ev.method === "string") rows.push({ k: "Method", v: ev.method });
  if (typeof ev.unit === "string") rows.push({ k: "Unit", v: ev.unit });
  if (typeof ev.trigger_mode === "string") rows.push({ k: "Trigger", v: ev.trigger_mode });
  if (ev.baseline_date) rows.push({ k: "Baseline date", v: String(ev.baseline_date) });
  if (typeof ev.n === "number") rows.push({ k: "n", v: String(ev.n) });
  if (typeof ev.lookback === "number") rows.push({ k: "Lookback", v: String(ev.lookback) });
  if (typeof ev.z === "number") rows.push({ k: "z", v: ev.z.toFixed(2) });

  if (!rows.length) return null;

  return (
    <div className="glass-card rounded-xl p-4">
      <div className="text-white/60 text-xs">Bằng chứng (tóm tắt)</div>
      <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
        {rows.map((r) => (
          <div key={r.k} className="flex items-center justify-between gap-3">
            <div className="text-white/50">{r.k}</div>
            <div className="text-white/90 font-medium">{r.v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TransmissionClient({
  initialLatest,
  initialScoreSeries,
  initialAlerts,
  initialCoverage,
  initialProgress,
  initialScoreSummary,
  initialDate,
  defaultRangeStart,
  defaultRangeEnd,
}: {
  initialLatest: TransmissionMetricRecord[];
  initialScoreSeries: TransmissionMetricRecord[];
  initialAlerts: TransmissionAlertRecord[];
  initialCoverage: TransmissionCoverageSummary | null;
  initialProgress: TransmissionProgressSummary | null;
  initialScoreSummary: TransmissionScoreSummary | null;
  initialDate: string;
  defaultRangeStart: string;
  defaultRangeEnd: string;
}) {
  const [latest, setLatest] = useState(initialLatest);
  const [scoreSeries, setScoreSeries] = useState(initialScoreSeries);
  const [alerts, setAlerts] = useState(initialAlerts);
  const [coverage, setCoverage] = useState<TransmissionCoverageSummary | null>(initialCoverage);
  const [progress, setProgress] = useState<TransmissionProgressSummary | null>(initialProgress);
  const [scoreSummary, setScoreSummary] = useState<TransmissionScoreSummary | null>(initialScoreSummary);

  const [computeDate, setComputeDate] = useState(initialDate);
  const [rangeStart, setRangeStart] = useState(defaultRangeStart);
  const [rangeEnd, setRangeEnd] = useState(defaultRangeEnd);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [filterType, setFilterType] = useState<string>("ALL");
  const [filterSeverity, setFilterSeverity] = useState<string>("ALL");
  const [search, setSearch] = useState<string>("");
  const [selectedAlert, setSelectedAlert] = useState<TransmissionAlertRecord | null>(null);

  const dict = useMemo(() => {
    const d: Record<string, TransmissionMetricRecord> = {};
    for (const m of latest) d[m.metric_name] = m;
    return d;
  }, [latest]);

  const latestDate = latest[0]?.date || initialDate;
  const transmissionScore = dict["transmission_score"]?.metric_value ?? null;
  const regimeBucket = dict["regime_bucket"]?.metric_value_text ?? null;
  const level10y = dict["level_10y"]?.metric_value ?? null;
  const slope10y2y = dict["slope_10y_2y"]?.metric_value ?? null;
  const ibOn = dict["ib_on"]?.metric_value ?? null;

  const scoreChart = useMemo(() => {
    return [...scoreSeries]
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((r) => ({
        date: r.date,
        score: r.metric_value ?? null,
      }));
  }, [scoreSeries]);

  const alertTypes = useMemo(() => {
    const types = new Set<string>();
    for (const a of alerts) types.add(a.alert_type);
    return ["ALL", ...Array.from(types).sort()];
  }, [alerts]);

  const filteredAlerts = useMemo(() => {
    const q = search.trim().toLowerCase();
    return [...alerts]
      .filter((a) => (filterType === "ALL" ? true : a.alert_type === filterType))
      .filter((a) => (filterSeverity === "ALL" ? true : a.severity === filterSeverity))
      .filter((a) => {
        if (!q) return true;
        return (
          a.alert_type.toLowerCase().includes(q) ||
          (a.message || "").toLowerCase().includes(q) ||
          (a.severity || "").toLowerCase().includes(q)
        );
      })
      .sort((a, b) => {
        const da = new Date(a.date as any).getTime();
        const db = new Date(b.date as any).getTime();
        if (db !== da) return db - da;
        return b.id - a.id;
      });
  }, [alerts, filterType, filterSeverity, search]);

  async function refresh() {
    setErr(null);
    const [l, s, a] = await Promise.all([
      bondlabApi.transmissionLatest(),
      bondlabApi.transmissionTimeseries({ metric_name: "transmission_score", limit: 90 }),
      bondlabApi.transmissionAlerts({ limit: 30 }),
    ]);
    setLatest(l);
    setScoreSeries(s);
    setAlerts(a);
  }

  async function refreshDiagnostics() {
    if (!rangeStart || !rangeEnd) return;
    const [cov, prog, sum] = await Promise.all([
      bondlabApi.transmissionCoverage(rangeStart, rangeEnd),
      bondlabApi.transmissionProgress(rangeStart, rangeEnd),
      bondlabApi.transmissionScoreSummary(rangeStart, rangeEnd),
    ]);
    setCoverage(cov);
    setProgress(prog);
    setScoreSummary(sum);
  }

  async function computeOne() {
    if (!computeDate) return;
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>(`/api/admin/transmission/compute?target_date=${encodeURIComponent(computeDate)}`);
      setMsg(`Đã compute transmission: ${res?.date} (metrics=${res?.metrics_count}, alerts=${res?.alerts_count})`);
      await refresh();
      await refreshDiagnostics();
    } catch (e: any) {
      setErr(e?.message || "Compute thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function computeRange() {
    if (!rangeStart || !rangeEnd) return;
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>(
        `/api/admin/transmission/compute-range?start_date=${encodeURIComponent(rangeStart)}&end_date=${encodeURIComponent(rangeEnd)}&skip_existing=true`
      );
      setMsg(
        `Đã compute range: processed=${res?.processed}, ok=${res?.succeeded}, failed=${res?.failed} (pending=${res?.pending_dates})`
      );
      await refresh();
      await refreshDiagnostics();
    } catch (e: any) {
      setErr(e?.message || "Compute range thất bại");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    setComputeDate(initialDate);
  }, [initialDate]);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Transmission</h1>
          <p className="text-white/60 mt-2">
            Bond Transmission Analytics (tổng hợp chỉ số + cảnh báo + kiểm tra coverage).
          </p>
        </div>
      </div>

      {(msg || err) && (
        <GlassCard>
          {msg && <div className="text-emerald-200 text-sm">{msg}</div>}
          {err && <div className="text-red-300 text-sm">{err}</div>}
        </GlassCard>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Hôm nay</div>
          <div className="text-white text-2xl font-bold">{latestDate || "—"}</div>
          <div className="text-white/50 text-sm">Regime: <span className="text-white/80 font-semibold">{regimeBucket || "—"}</span></div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Transmission score</div>
          <div className="text-white text-2xl font-bold">{fmtScore(transmissionScore)}</div>
          <div className="text-white/50 text-sm">Thang 0–100 (càng cao càng “tight”).</div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Quick signals</div>
          <div className="text-white/70 text-sm">10Y: <span className="text-white/90 font-semibold">{fmtPct(level10y)}</span></div>
          <div className="text-white/70 text-sm">Slope 10Y–2Y: <span className="text-white/90 font-semibold">{fmtBpsFromPct(slope10y2y)}</span></div>
          <div className="text-white/70 text-sm">IB O/N: <span className="text-white/90 font-semibold">{fmtPct(ibOn)}</span></div>
        </GlassCard>
      </div>

      <GlassCard>
        <div className="flex items-end justify-between gap-4 flex-wrap mb-4">
          <div>
            <div className="text-white font-semibold">Transmission score (series)</div>
            <div className="text-white/50 text-sm">90 điểm gần nhất (nếu có).</div>
          </div>
          <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" onClick={() => refresh()}>
            Refresh
          </button>
        </div>
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={scoreChart}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis dataKey="date" stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} />
            <YAxis stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} domain={[0, 100]} />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(15, 23, 42, 0.9)",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "12px",
              }}
              labelStyle={{ color: "rgba(255,255,255,0.8)" }}
              formatter={(value: any) => (value == null ? "—" : Number(value).toFixed(1))}
            />
            <Line type="monotone" dataKey="score" stroke="#00C897" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </GlassCard>

      <GlassCard className="space-y-3">
        <div className="text-white font-semibold">Cảnh báo gần đây</div>
        <details className="text-sm text-white/60">
          <summary className="cursor-pointer select-none">
            Cơ chế (giải thích ngắn)
          </summary>
          <div className="mt-2 space-y-1 text-white/60">
            <div>
              Cảnh báo được tạo ngay sau khi hệ thống “compute Transmission” theo ngày. Mỗi cảnh báo là 1{" "}
              <span className="text-white/80">quy tắc phát hiện bất thường</span> (không phải khuyến nghị hành động).
            </div>
            <div>
              Nguồn dữ liệu: Yield curve (HNX), Interbank (SBV), Auction, Secondary, Policy. Nếu thiếu dữ liệu ở phần nào thì cảnh báo liên quan có thể không xuất hiện.
            </div>
            <div>
              Ví dụ điều kiện: (1) Transmission score z-score 120 quan sát gần nhất cao; (2) O/N spike (z≥2 hoặc O/N≥2%); (3) dốc 10Y–2Y cao; (4) BTC thấp; (5) thanh khoản thứ cấp giảm; (6) thay đổi lãi suất điều hành.
            </div>
          </div>
        </details>

        <div className="flex items-center gap-2 flex-wrap">
          <select
            className="glass-input px-3 py-2 rounded-lg text-white text-sm"
            value={filterSeverity}
            onChange={(e) => setFilterSeverity(e.target.value)}
          >
            <option value="ALL">Tất cả mức</option>
            <option value="HIGH">HIGH</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="LOW">LOW</option>
          </select>
          <select
            className="glass-input px-3 py-2 rounded-lg text-white text-sm"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            {alertTypes.map((t) => (
              <option key={t} value={t}>
                {t === "ALL" ? "Tất cả loại" : t}
              </option>
            ))}
          </select>
          <input
            className="glass-input px-3 py-2 rounded-lg text-white text-sm min-w-[240px]"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Tìm trong loại/mức/thông điệp…"
          />
          <div className="text-white/60 text-sm">
            {filteredAlerts.length}/{alerts.length} cảnh báo
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px]">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Ngày</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Loại</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Mức</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Thông điệp</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Giá trị</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Ngưỡng</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60"> </th>
              </tr>
            </thead>
            <tbody>
              {filteredAlerts.map((a) => (
                <tr
                  key={a.id}
                  className={`border-b border-white/5 hover:bg-white/5 ${
                    a.severity === "HIGH" ? "bg-red-500/5" : a.severity === "MEDIUM" ? "bg-amber-500/5" : ""
                  }`}
                >
                  <td className="py-2 px-3 text-white">{a.date}</td>
                  <td className="py-2 px-3">
                    <div className="text-white/90">{alertTypeLabel(a.alert_type)}</div>
                    <div className="text-white/50 text-xs">{a.alert_type}</div>
                  </td>
                  <td className={`py-2 px-3 font-semibold ${severityClass(a.severity)}`}>{a.severity}</td>
                  <td className="py-2 px-3 text-white/70">{a.message}</td>
                  <td className="py-2 px-3 text-right text-white/90">{fmtAlertValue(a)}</td>
                  <td className="py-2 px-3 text-right text-white/60">{fmtAlertThreshold(a)}</td>
                  <td className="py-2 px-3 text-right">
                    <button
                      className="glass-button px-3 py-1.5 rounded-lg text-white text-xs hover:bg-white/10"
                      onClick={() => setSelectedAlert(a)}
                    >
                      Chi tiết
                    </button>
                  </td>
                </tr>
              ))}
              {filteredAlerts.length === 0 ? (
                <tr>
                  <td className="py-6 px-3 text-white/60" colSpan={7}>
                    Không có cảnh báo khớp bộ lọc.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {selectedAlert ? (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => setSelectedAlert(null)}
        >
          <div className="w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
            <GlassCard className="space-y-3">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-white font-semibold text-lg">{alertTypeLabel(selectedAlert.alert_type)}</div>
                  <div className="text-white/50 text-sm">
                    {selectedAlert.date} • <span className={severityClass(selectedAlert.severity)}>{selectedAlert.severity}</span> •{" "}
                    <span className="text-white/60">{selectedAlert.alert_type}</span>
                  </div>
                </div>
                <button
                  className="glass-button px-3 py-1.5 rounded-lg text-white text-xs hover:bg-white/10"
                  onClick={() => setSelectedAlert(null)}
                >
                  Đóng
                </button>
              </div>

              <div className="text-white/70 text-sm">{alertExplain(selectedAlert.alert_type)}</div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="text-white/80 text-sm">
                  <div className="text-white/60 text-xs">Giá trị</div>
                  <div className="text-white font-semibold">{fmtAlertValue(selectedAlert)}</div>
                </div>
                <div className="text-white/80 text-sm">
                  <div className="text-white/60 text-xs">Ngưỡng</div>
                  <div className="text-white font-semibold">{fmtAlertThreshold(selectedAlert)}</div>
                </div>
              </div>

              <EvidenceSummary alert={selectedAlert} />

              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="text-white/60 text-xs">
                  Đây là thông tin về điều kiện thị trường, không phải khuyến nghị tài chính.
                </div>
                <a
                  className="glass-button px-3 py-1.5 rounded-lg text-white text-xs hover:bg-white/10"
                  href={alertLink(selectedAlert.alert_type).href}
                >
                  {alertLink(selectedAlert.alert_type).label} →
                </a>
              </div>

              <details className="text-white/60 text-sm">
                <summary className="cursor-pointer select-none">source_data (kỹ thuật)</summary>
                <pre className="mt-2 text-xs text-white/70 whitespace-pre-wrap break-words">
{(() => {
  try {
    const raw = (selectedAlert as any).source_data;
    const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    return JSON.stringify(parsed ?? {}, null, 2);
  } catch {
    return String((selectedAlert as any).source_data ?? "");
  }
})()}
                </pre>
              </details>
            </GlassCard>
          </div>
        </div>
      ) : null}

      <GlassCard className="space-y-3">
        <div className="text-white font-semibold">Diagnostics (coverage / progress / distribution)</div>
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="date"
            value={rangeStart}
            onChange={(e) => setRangeStart(e.target.value)}
            className="glass-input px-4 py-2 rounded-lg text-white text-sm"
          />
          <input
            type="date"
            value={rangeEnd}
            onChange={(e) => setRangeEnd(e.target.value)}
            className="glass-input px-4 py-2 rounded-lg text-white text-sm"
          />
          <button
            className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
            disabled={busy || !rangeStart || !rangeEnd}
            onClick={() => refreshDiagnostics()}
          >
            Refresh diagnostics
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <GlassCard className="space-y-1">
            <div className="text-white/60 text-sm">Coverage</div>
            <div className="text-white/80 text-sm">
              Total dates: <span className="text-white font-semibold">{coverage?.dates_total ?? "—"}</span>
            </div>
            <div className="text-white/80 text-sm">
              Score computable (k≥3): <span className="text-white font-semibold">{coverage?.score_computable ?? "—"}</span>
            </div>
          </GlassCard>
          <GlassCard className="space-y-1">
            <div className="text-white/60 text-sm">Progress</div>
            <div className="text-white/80 text-sm">
              Source dates: <span className="text-white font-semibold">{progress?.source_dates_total ?? "—"}</span>
            </div>
            <div className="text-white/80 text-sm">
              Score computed: <span className="text-white font-semibold">{progress?.score_computed_dates ?? "—"}</span>
            </div>
          </GlassCard>
          <GlassCard className="space-y-1">
            <div className="text-white/60 text-sm">Score distribution</div>
            <div className="text-white/80 text-sm">
              n: <span className="text-white font-semibold">{scoreSummary?.n ?? "—"}</span>
            </div>
            <div className="text-white/80 text-sm">
              p20/p50/p80:{" "}
              <span className="text-white font-semibold">
                {scoreSummary?.p20 == null ? "—" : scoreSummary.p20.toFixed(1)}
              </span>{" "}
              /{" "}
              <span className="text-white font-semibold">
                {scoreSummary?.p50 == null ? "—" : scoreSummary.p50.toFixed(1)}
              </span>{" "}
              /{" "}
              <span className="text-white font-semibold">
                {scoreSummary?.p80 == null ? "—" : scoreSummary.p80.toFixed(1)}
              </span>
            </div>
          </GlassCard>
        </div>
      </GlassCard>

      <GlassCard className="space-y-3">
        <div className="text-white font-semibold">Compute (admin)</div>
        <div className="text-white/50 text-sm">
          Dùng khi cần rebuild metrics/alerts. Bình thường hệ thống daily ingest sẽ tự cập nhật.
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="date"
            value={computeDate}
            onChange={(e) => setComputeDate(e.target.value)}
            className="glass-input px-4 py-2 rounded-lg text-white text-sm"
          />
          <button
            className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
            disabled={busy || !computeDate}
            onClick={() => computeOne()}
          >
            Compute 1 ngày
          </button>
          <button
            className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
            disabled={busy || !rangeStart || !rangeEnd}
            onClick={() => computeRange()}
          >
            Compute range
          </button>
        </div>
      </GlassCard>
    </div>
  );
}
