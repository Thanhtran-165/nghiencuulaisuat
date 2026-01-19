"use client";

import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import {
  bondlabApi,
  CausalitySeriesCoverage,
  CausalitySeriesInfo,
  GrangerResult,
  LeadLagResult,
} from "@/lib/bondlabApi";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function fmtCorr(v?: number | null) {
  if (v == null) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(3)}`;
}

function fmtP(v?: number | null) {
  if (v == null) return "—";
  if (v < 0.0001) return "<0.0001";
  return v.toFixed(4);
}

function strengthLabel(absCorr: number) {
  if (absCorr < 0.2) return { label: "Yếu", tone: "muted" as const };
  if (absCorr < 0.4) return { label: "Vừa", tone: "info" as const };
  if (absCorr < 0.6) return { label: "Mạnh", tone: "good" as const };
  return { label: "Rất mạnh", tone: "good" as const };
}

function toneClass(tone: "muted" | "info" | "good" | "warn") {
  if (tone === "good") return "bg-emerald-500/20 text-emerald-200 border-emerald-400/20";
  if (tone === "warn") return "bg-amber-500/20 text-amber-200 border-amber-400/20";
  if (tone === "info") return "bg-sky-500/20 text-sky-200 border-sky-400/20";
  return "bg-white/5 text-white/70 border-white/10";
}

function Badge({
  label,
  tone,
}: {
  label: string;
  tone: "muted" | "info" | "good" | "warn";
}) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${toneClass(tone)}`}>
      {label}
    </span>
  );
}

function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button className="absolute inset-0 bg-black/60" aria-label="Close modal" onClick={onClose} />
      <div className="relative w-full max-w-3xl">
        <GlassCard className="p-0 overflow-hidden">
          <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between gap-3">
            <div className="text-white font-semibold">{title}</div>
            <button className="glass-button px-3 py-1.5 rounded-lg text-white/80 hover:text-white" onClick={onClose}>
              Đóng
            </button>
          </div>
          <div className="px-6 py-5">{children}</div>
        </GlassCard>
      </div>
    </div>
  );
}

type Preset = {
  id: string;
  title: string;
  question: string;
  x: string;
  y: string;
  diff: boolean;
  maxLag: number;
};

const PRESETS: Preset[] = [
  {
    id: "ib_on__yield_10y",
    title: "Liên ngân hàng → Lợi suất 10Y",
    question: "Lãi suất liên ngân hàng O/N có thường đi trước lợi suất TPCP 10 năm không?",
    x: "ib_on",
    y: "yield_10y",
    diff: true,
    maxLag: 20,
  },
  {
    id: "ib_on__bank_deposit_avg_12m",
    title: "IB O/N → Tiền gửi TB (12T)",
    question: "Lãi suất liên ngân hàng O/N có thường đi trước lãi suất tiền gửi trung bình 12 tháng không?",
    x: "ib_on",
    y: "bank_deposit_avg_12m",
    diff: true,
    maxLag: 20,
  },
  {
    id: "ib_on__bank_loan_avg",
    title: "IB O/N → Cho vay TB",
    question: "Lãi suất liên ngân hàng O/N có thường đi trước lãi suất cho vay trung bình không?",
    x: "ib_on",
    y: "bank_loan_avg",
    diff: true,
    maxLag: 20,
  },
  {
    id: "yield_10y__bank_deposit_avg_12m",
    title: "VN10Y → Tiền gửi TB (12T)",
    question: "Lợi suất TPCP 10 năm có thường đi trước lãi suất tiền gửi trung bình 12 tháng không?",
    x: "yield_10y",
    y: "bank_deposit_avg_12m",
    diff: true,
    maxLag: 20,
  },
  {
    id: "yield_10y__bank_loan_avg",
    title: "VN10Y → Cho vay TB",
    question: "Lợi suất TPCP 10 năm có thường đi trước lãi suất cho vay trung bình không?",
    x: "yield_10y",
    y: "bank_loan_avg",
    diff: true,
    maxLag: 20,
  },
  {
    id: "yield_2y__bank_deposit_avg_12m",
    title: "VN2Y → Tiền gửi TB (12T)",
    question: "Lợi suất TPCP 2 năm có thường đi trước lãi suất tiền gửi trung bình 12 tháng không?",
    x: "yield_2y",
    y: "bank_deposit_avg_12m",
    diff: true,
    maxLag: 20,
  },
  {
    id: "yield_2y__bank_loan_avg",
    title: "VN2Y → Cho vay TB",
    question: "Lợi suất TPCP 2 năm có thường đi trước lãi suất cho vay trung bình không?",
    x: "yield_2y",
    y: "bank_loan_avg",
    diff: true,
    maxLag: 20,
  },
  {
    id: "slope_10y_2y__bank_deposit_avg_12m",
    title: "Độ dốc (10Y–2Y) → Tiền gửi TB (12T)",
    question: "Độ dốc đường cong (10Y–2Y) có thường đi trước lãi suất tiền gửi trung bình 12 tháng không?",
    x: "slope_10y_2y",
    y: "bank_deposit_avg_12m",
    diff: true,
    maxLag: 20,
  },
  {
    id: "slope_10y_2y__bank_loan_avg",
    title: "Độ dốc (10Y–2Y) → Cho vay TB",
    question: "Độ dốc đường cong (10Y–2Y) có thường đi trước lãi suất cho vay trung bình không?",
    x: "slope_10y_2y",
    y: "bank_loan_avg",
    diff: true,
    maxLag: 20,
  },
  {
    id: "auction_btc__yield_10y",
    title: "Đấu thầu (BTC) → Lợi suất 10Y",
    question: "Kết quả đấu thầu (BTC) có thường đi trước biến động lợi suất 10Y không?",
    x: "auction_btc",
    y: "yield_10y",
    diff: true,
    maxLag: 20,
  },
  {
    id: "secondary_value__yield_10y",
    title: "Thứ cấp → Lợi suất 10Y",
    question: "Giá trị giao dịch thứ cấp có thường đi trước lợi suất 10Y không?",
    x: "secondary_value",
    y: "yield_10y",
    diff: true,
    maxLag: 20,
  },
  {
    id: "us10y__yield_10y",
    title: "US10Y → VN10Y",
    question: "US 10Y có thường đi trước VN 10Y không? (nếu có dữ liệu FRED)",
    x: "us10y",
    y: "yield_10y",
    diff: true,
    maxLag: 20,
  },
  {
    id: "stress__transmission",
    title: "Stress ↔ Transmission",
    question: "Stress index và Transmission score có quan hệ dẫn dắt (theo thống kê) không?",
    x: "stress_index",
    y: "transmission_score",
    diff: true,
    maxLag: 20,
  },
];

const VI_LABELS: Record<string, { label: string; unitHint?: string; group: string }> = {
  yield_10y: { label: "Lợi suất TPCP 10 năm (VN10Y)", unitHint: "%/năm", group: "Lợi suất" },
  yield_2y: { label: "Lợi suất TPCP 2 năm (VN2Y)", unitHint: "%/năm", group: "Lợi suất" },
  slope_10y_2y: { label: "Độ dốc đường cong (10Y–2Y)", unitHint: "điểm %", group: "Lợi suất" },
  auction_btc: { label: "Đấu thầu: Bid-to-cover (BTC, trung vị)", unitHint: "lần", group: "Đấu thầu" },
  auction_sold: { label: "Đấu thầu: Khối lượng trúng (tổng)", unitHint: "VND", group: "Đấu thầu" },
  secondary_value: { label: "Thứ cấp: Giá trị giao dịch (tổng)", unitHint: "VND", group: "Thứ cấp" },
  bank_deposit_avg_12m: { label: "Tiền gửi TB 12T (bình quân theo ngân hàng)", unitHint: "%/năm", group: "Lãi suất NH" },
  bank_loan_avg: { label: "Cho vay TB (bình quân theo ngân hàng)", unitHint: "%/năm", group: "Lãi suất NH" },
  ib_on: { label: "Liên ngân hàng O/N", unitHint: "%/năm", group: "Tiền tệ" },
  policy_anchor: { label: "Lãi suất điều hành (anchor)", unitHint: "%/năm", group: "Tiền tệ" },
  us10y: { label: "US 10Y (FRED)", unitHint: "%/năm", group: "Toàn cầu" },
  spread_vn10y_us10y: { label: "Chênh lệch VN10Y − US10Y", unitHint: "điểm %", group: "Toàn cầu" },
  transmission_score: { label: "Transmission score", unitHint: "0–100", group: "Tổng hợp" },
  stress_index: { label: "BondY Stress index", unitHint: "0–100", group: "Tổng hợp" },
};

const SERIES_GROUPS = ["Tổng hợp", "Lợi suất", "Tiền tệ", "Lãi suất NH", "Đấu thầu", "Thứ cấp", "Toàn cầu", "Khác"] as const;

function seriesShortLabel(id: string, seriesMap: Record<string, CausalitySeriesInfo>): string {
  const s = seriesMap[id];
  if (!s) return id;
  return VI_LABELS[id]?.label || s.label || id;
}

function seriesOptionLabel(s: CausalitySeriesInfo): string {
  const main = VI_LABELS[s.id]?.label || s.label || s.id;
  const unit = VI_LABELS[s.id]?.unitHint || s.unit;
  return `${main}${unit ? ` · ${unit}` : ""}`;
}

function interpretLeadLag(leadLag: LeadLagResult | null, xLabel: string, yLabel: string) {
  if (!leadLag || leadLag.best_lag == null || leadLag.best_corr == null) {
    return {
      headline: "Chưa đủ dữ liệu để kết luận.",
      strength: null as null | ReturnType<typeof strengthLabel>,
      confidence: { label: "Thấp", tone: "muted" as const },
      sameOpposite: null as null | string,
    };
  }

  const lag = leadLag.best_lag;
  const corr = leadLag.best_corr;
  const abs = Math.abs(corr);

  const whoLeads =
    lag > 0
      ? `${xLabel} thường đi trước ${yLabel} ~${lag} phiên`
      : lag < 0
        ? `${yLabel} thường đi trước ${xLabel} ~${Math.abs(lag)} phiên`
        : "Hai chuỗi gần như đồng thời (lag=0)";
  const sameOpp = corr >= 0 ? "Cùng chiều" : "Ngược chiều";
  const str = strengthLabel(abs);

  const pAdj = leadLag.best_p_value_adj ?? null;
  const nPairs = leadLag.best_n_pairs ?? null;
  const stable = Boolean((leadLag.stability as any)?.enabled && (leadLag.stability as any)?.consistent);

  let confidence: { label: string; tone: "muted" | "info" | "good" | "warn" } = { label: "Thấp", tone: "muted" };
  if (nPairs != null && nPairs >= 30 && pAdj != null && pAdj < 0.05 && stable) confidence = { label: "Cao", tone: "good" };
  else if (nPairs != null && nPairs >= 20 && pAdj != null && pAdj < 0.1) confidence = { label: "Vừa", tone: "info" };
  else if (nPairs != null && nPairs >= 20) confidence = { label: "Thấp", tone: "warn" };

  return {
    headline: `${whoLeads} • ${sameOpp}`,
    strength: str,
    confidence,
    sameOpposite: sameOpp,
  };
}

export function CausalityClient({
  initialSeries,
  initialCoverage,
  defaultStart,
  defaultEnd,
}: {
  initialSeries: CausalitySeriesInfo[];
  initialCoverage: CausalitySeriesCoverage[];
  defaultStart: string;
  defaultEnd: string;
}) {
  const [series, setSeries] = useState<CausalitySeriesInfo[]>(initialSeries);
  const [coverage, setCoverage] = useState<CausalitySeriesCoverage[]>(initialCoverage);
  const [start, setStart] = useState(defaultStart);
  const [end, setEnd] = useState(defaultEnd);

  const [guided, setGuided] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);

  const [presetId, setPresetId] = useState<string>(() => PRESETS[0]?.id || "");

  const [x, setX] = useState<string>(() => PRESETS[0]?.x || initialSeries[0]?.id || "yield_10y");
  const [y, setY] = useState<string>(() => PRESETS[0]?.y || initialSeries[1]?.id || "ib_on");
  const [diff, setDiff] = useState(true);
  const [maxLag, setMaxLag] = useState(20);

  const [leadLag, setLeadLag] = useState<LeadLagResult | null>(null);
  const [granger, setGranger] = useState<GrangerResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const seriesMap = useMemo(() => {
    const m: Record<string, CausalitySeriesInfo> = {};
    for (const s of series) m[s.id] = s;
    return m;
  }, [series]);

  const coverageMap = useMemo(() => {
    const m: Record<string, CausalitySeriesCoverage> = {};
    for (const c of coverage) m[c.series_id] = c;
    return m;
  }, [coverage]);

  const preset = useMemo(() => PRESETS.find((p) => p.id === presetId) || null, [presetId]);

  const availablePresets = useMemo(() => {
    return PRESETS.map((p) => {
      const hasX = Boolean(seriesMap[p.x]);
      const hasY = Boolean(seriesMap[p.y]);
      const xObs = coverageMap[p.x]?.n_obs ?? 0;
      const yObs = coverageMap[p.y]?.n_obs ?? 0;
      const minObs = Math.min(xObs, yObs);
      return { preset: p, ok: hasX && hasY && minObs >= 10, minObs, hasX, hasY };
    });
  }, [seriesMap, coverageMap]);

  useEffect(() => {
    if (!guided) return;
    const p = PRESETS.find((pp) => pp.id === presetId);
    if (!p) return;
    setX(p.x);
    setY(p.y);
    setDiff(p.diff);
    setMaxLag(p.maxLag);
    setLeadLag(null);
    setGranger(null);
  }, [guided, presetId]);

  const xLabel = useMemo(() => seriesShortLabel(x, seriesMap), [x, seriesMap]);
  const yLabel = useMemo(() => seriesShortLabel(y, seriesMap), [y, seriesMap]);

  const xCov = coverageMap[x]?.n_obs ?? 0;
  const yCov = coverageMap[y]?.n_obs ?? 0;
  const minObs = Math.min(xCov, yCov);
  const readinessNote = minObs >= 30 ? "Có thể chạy lead‑lag cơ bản." : "Dữ liệu còn mỏng; kết quả chỉ mang tính gợi ý.";

  const interp = useMemo(() => interpretLeadLag(leadLag, xLabel, yLabel), [leadLag, xLabel, yLabel]);

  const leadLagBars = useMemo(() => {
    if (!leadLag) return [];
    return leadLag.lags.map((lag, idx) => ({
      lag,
      corr: leadLag.correlations[idx] ?? null,
      nPairs: leadLag.n_pairs_by_lag?.[idx] ?? null,
      pAdj: leadLag.p_values_adj?.[idx] ?? null,
      ciLow: leadLag.ci95_low?.[idx] ?? null,
      ciHigh: leadLag.ci95_high?.[idx] ?? null,
    }));
  }, [leadLag]);

  async function refreshCatalog() {
    setErr(null);
    const [s, c] = await Promise.all([
      bondlabApi.causalitySeries(),
      bondlabApi.causalityAvailability(start, end),
    ]);
    setSeries(s);
    setCoverage(c);
  }

  async function runLeadLag() {
    try {
      setBusy(true);
      setErr(null);
      const res = await bondlabApi.causalityLeadLag({
        x,
        y,
        start_date: start,
        end_date: end,
        max_lag: maxLag,
        diff,
      });
      setLeadLag(res);
      setGranger(null);
    } catch (e: any) {
      setErr(e?.message || "Không thể chạy lead-lag");
    } finally {
      setBusy(false);
    }
  }

  async function runGranger() {
    try {
      setBusy(true);
      setErr(null);
      const res = await bondlabApi.causalityGranger({
        cause: x,
        effect: y,
        start_date: start,
        end_date: end,
        max_lag: Math.min(10, Math.max(1, Math.floor(maxLag / 4))),
        diff,
      });
      setGranger(res);
    } catch (e: any) {
      setErr(e?.message || "Không thể chạy Granger");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Ai dẫn ai?</h1>
          <p className="text-white/60 mt-2">
            Công cụ “dẫn dắt & độ trễ”: xem chuỗi nào thường đi trước chuỗi nào. Đây là mô tả thống kê, không khẳng định nhân quả.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            className={`glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 ${guided ? "active" : ""}`}
            onClick={() => setGuided(true)}
          >
            Bắt đầu nhanh
          </button>
          <button
            className={`glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 ${!guided ? "active" : ""}`}
            onClick={() => setGuided(false)}
          >
            Nâng cao
          </button>
          <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" onClick={() => setHelpOpen(true)}>
            Giải thích
          </button>
          <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" onClick={() => refreshCatalog()}>
            Refresh dữ liệu
          </button>
        </div>
      </div>

      {err && (
        <GlassCard>
          <div className="text-red-300 text-sm">{err}</div>
        </GlassCard>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="space-y-3 lg:col-span-2">
          <div className="text-white font-semibold">Dẫn dắt (độ trễ)</div>
          <div className="text-white/50 text-sm">
            {readinessNote} Dải thời gian: {start} → {end}
          </div>

          {guided ? (
            <div className="glass-card rounded-xl p-4">
              <div className="text-white/60 text-xs">Chọn câu hỏi (preset)</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
                <div className="space-y-1">
                  <select
                    value={presetId}
                    onChange={(e) => setPresetId(e.target.value)}
                    className="glass-input w-full px-4 py-2 rounded-lg text-white text-sm"
                  >
                    {availablePresets.map((p) => (
                      <option key={p.preset.id} value={p.preset.id} disabled={!p.hasX || !p.hasY}>
                        {p.preset.title}
                      </option>
                    ))}
                  </select>
                  <div className="text-white/60 text-sm mt-2">{preset?.question}</div>
                  <div className="text-white/40 text-xs">
                    {(() => {
                      const cur = availablePresets.find((pp) => pp.preset.id === presetId);
                      if (!cur) return null;
                      if (!cur.hasX || !cur.hasY) return "Cặp preset này chưa sẵn sàng (thiếu chuỗi).";
                      return `Độ phủ (overlap≈min): ~${cur.minObs} phiên`;
                    })()}
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="text-white/60 text-xs">Cặp chuỗi đang dùng</div>
                  <div className="text-white/90 text-sm">
                    X: <span className="font-medium">{xLabel}</span>
                  </div>
                  <div className="text-white/90 text-sm">
                    Y: <span className="font-medium">{yLabel}</span>
                  </div>
                  <div className="text-white/40 text-xs mt-2">
                    X={xCov} phiên · Y={yCov} phiên · overlap≈{minObs}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-wrap mt-3">
                <label className="text-white/70 text-sm flex items-center gap-2">
                  <input type="checkbox" checked={diff} onChange={(e) => setDiff(e.target.checked)} />
                  So theo thay đổi (Δ) thay vì mức
                </label>
                <div className="flex items-center gap-2">
                  <span className="text-white/60 text-sm">Max lag</span>
                  <input
                    type="number"
                    value={maxLag}
                    onChange={(e) => setMaxLag(Number(e.target.value))}
                    min={1}
                    max={60}
                    className="glass-input w-[110px] px-3 py-2 rounded-lg text-white text-sm"
                  />
                </div>
                <button
                  className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
                  disabled={busy || !x || !y || !start || !end}
                  onClick={() => runLeadLag()}
                >
                  Chạy
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                <div className="space-y-1">
                  <div className="text-white/60 text-xs">Chuỗi X</div>
                  <select value={x} onChange={(e) => setX(e.target.value)} className="glass-input w-full px-4 py-2 rounded-lg text-white text-sm">
                    {SERIES_GROUPS.map((group) => (
                      <optgroup key={group} label={group}>
                        {series
                          .filter((s) => (VI_LABELS[s.id]?.group || "Khác") === group)
                          .map((s) => (
                            <option key={s.id} value={s.id}>
                              {seriesOptionLabel(s)}
                            </option>
                          ))}
                      </optgroup>
                    ))}
                  </select>
                  <div className="text-white/40 text-xs">
                    Có {xCov} phiên trong khoảng chọn. <span className="text-white/50">ID: {x}</span>
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="text-white/60 text-xs">Chuỗi Y</div>
                  <select value={y} onChange={(e) => setY(e.target.value)} className="glass-input w-full px-4 py-2 rounded-lg text-white text-sm">
                    {SERIES_GROUPS.map((group) => (
                      <optgroup key={group} label={group}>
                        {series
                          .filter((s) => (VI_LABELS[s.id]?.group || "Khác") === group)
                          .map((s) => (
                            <option key={s.id} value={s.id}>
                              {seriesOptionLabel(s)}
                            </option>
                          ))}
                      </optgroup>
                    ))}
                  </select>
                  <div className="text-white/40 text-xs">
                    Có {yCov} phiên trong khoảng chọn. <span className="text-white/50">ID: {y}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-wrap mt-3">
                <label className="text-white/70 text-sm flex items-center gap-2">
                  <input type="checkbox" checked={diff} onChange={(e) => setDiff(e.target.checked)} />
                  So theo thay đổi (Δ) thay vì mức
                </label>
                <div className="flex items-center gap-2">
                  <span className="text-white/60 text-sm">Max lag</span>
                  <input
                    type="number"
                    value={maxLag}
                    onChange={(e) => setMaxLag(Number(e.target.value))}
                    min={1}
                    max={60}
                    className="glass-input w-[110px] px-3 py-2 rounded-lg text-white text-sm"
                  />
                </div>
                <button
                  className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
                  disabled={busy || !x || !y || !start || !end}
                  onClick={() => runLeadLag()}
                >
                  Chạy
                </button>
              </div>
            </>
          )}

          <div className="mt-4 space-y-2">
            <div className="text-white/80 text-sm">
              <span className="text-white/60">Kết luận:</span> {leadLag ? interp.headline : "Chưa chạy."}
            </div>
            {leadLag ? (
              <div className="flex items-center gap-2 flex-wrap">
                <Badge label={interp.sameOpposite || "—"} tone={interp.sameOpposite ? "info" : "muted"} />
                <Badge label={`Mức độ: ${interp.strength?.label || "—"}`} tone={interp.strength ? interp.strength.tone : "muted"} />
                <Badge label={`Tin cậy: ${interp.confidence.label}`} tone={interp.confidence.tone} />
              </div>
            ) : null}
          </div>

          {leadLag ? (
            <details className="mt-3">
              <summary className="cursor-pointer text-white/70 text-sm">Chi tiết nghiên cứu (ẩn/hiện)</summary>
              <div className="mt-2 text-white/60 text-sm space-y-1">
                <div>• “Phiên” = 1 quan sát theo ngày có dữ liệu (không phải lịch calendar).</div>
                <div>
                  • Overlap: <span className="text-white/80">{leadLag.n_overlap ?? "—"}</span> • Quét{" "}
                  <span className="text-white/80">{leadLag.m_tests ?? "—"}</span> mức lag.
                </div>
                <div>
                  • Best lag: <span className="text-white/80">{leadLag.best_lag ?? "—"}</span> • corr:{" "}
                  <span className="text-white/80">{fmtCorr(leadLag.best_corr)}</span>
                  {leadLag.best_p_value_adj != null ? (
                    <>
                      {" "}
                      • p_adj=<span className="text-white/80">{fmtP(leadLag.best_p_value_adj)}</span>
                    </>
                  ) : null}
                </div>
                <div>
                  • CI95:{" "}
                  <span className="text-white/80">
                    {leadLag.best_ci95_low == null || leadLag.best_ci95_high == null
                      ? "—"
                      : `[${leadLag.best_ci95_low.toFixed(3)}, ${leadLag.best_ci95_high.toFixed(3)}]`}
                  </span>
                  {leadLag.best_n_pairs != null ? (
                    <>
                      {" "}
                      • n_pairs=<span className="text-white/80">{leadLag.best_n_pairs}</span>
                    </>
                  ) : null}
                </div>
                {Array.isArray(leadLag.warnings) && leadLag.warnings.length ? (
                  <div>
                    • Lưu ý: <span className="text-white/80">{leadLag.warnings.join(", ")}</span>
                  </div>
                ) : null}
                <div className="text-white/40 text-xs">
                  Đây là mô tả thống kê (precedence) — không khẳng định “gây ra”. Khi thử nhiều cặp X/Y hoặc nhiều mức lag, rủi ro “tín hiệu giả”
                  tăng; p_adj giúp giảm rủi ro đó.
                </div>
              </div>
            </details>
          ) : null}

          <div className="mt-4">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={leadLagBars}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="lag" stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} />
                <YAxis stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} domain={[-1, 1]} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "rgba(15, 23, 42, 0.9)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: "12px",
                  }}
                  labelStyle={{ color: "rgba(255,255,255,0.8)" }}
                  formatter={(_value: any, _name: any, item: any) => {
                    const payload = item?.payload || {};
                    const corr = payload?.corr == null ? null : Number(payload.corr);
                    const nPairs = payload?.nPairs == null ? null : Number(payload.nPairs);
                    const pAdj = payload?.pAdj == null ? null : Number(payload.pAdj);
                    const ciLow = payload?.ciLow == null ? null : Number(payload.ciLow);
                    const ciHigh = payload?.ciHigh == null ? null : Number(payload.ciHigh);
                    const parts = [`corr=${fmtCorr(corr)}`];
                    if (nPairs != null) parts.push(`n=${nPairs}`);
                    if (ciLow != null && ciHigh != null) parts.push(`CI95=[${ciLow.toFixed(3)}, ${ciHigh.toFixed(3)}]`);
                    if (!guided && pAdj != null) parts.push(`p_adj=${fmtP(pAdj)}`);
                    return parts.join(" • ");
                  }}
                />
                <Bar dataKey="corr">
                  {leadLagBars.map((d, idx) => {
                    const sig = d.pAdj != null && d.pAdj < 0.05;
                    return <Cell key={idx} fill={sig ? "#00C897" : "#9D4EDD"} opacity={d.corr == null ? 0.2 : 1} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>

        <GlassCard className="space-y-2">
          <div className="text-white font-semibold">Nâng cao (tuỳ chọn)</div>
          <div className="text-white/50 text-sm">
            Kiểm định Granger cần dependency (statsmodels) ở backend. Nếu backend báo “disabled”, coi như chưa bật.
          </div>

          <button
            className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50 w-full"
            disabled={guided || busy || !x || !y}
            onClick={() => runGranger()}
            title={guided ? "Chuyển sang “Nâng cao” để dùng Granger" : undefined}
          >
            Chạy Granger (X → Y)
          </button>

          {granger ? (
            <div className="mt-2 space-y-2">
              {!granger.enabled ? (
                <div className="text-white/60 text-sm">
                  Disabled: <span className="text-white/80">{granger.reason || "unknown"}</span>
                </div>
              ) : (
                <>
                  <div className="text-white/60 text-sm">
                    n={granger.n_obs} • max_lag={granger.max_lag} • diff={String(granger.diff)}
                  </div>
                  {Array.isArray(granger.results) ? (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[420px]">
                        <thead>
                          <tr className="border-b border-white/10">
                            <th className="text-left py-2 px-3 text-sm font-medium text-white/60">lag</th>
                            <th className="text-right py-2 px-3 text-sm font-medium text-white/60">F</th>
                            <th className="text-right py-2 px-3 text-sm font-medium text-white/60">p</th>
                          </tr>
                        </thead>
                        <tbody>
                          {granger.results.map((r: any) => (
                            <tr key={r.lag} className="border-b border-white/5 hover:bg-white/5">
                              <td className="py-2 px-3 text-white/80">{r.lag}</td>
                              <td className="py-2 px-3 text-right text-white/90">
                                {r.f == null && r.f_stat == null ? "—" : Number(r.f ?? r.f_stat).toFixed(3)}
                              </td>
                              <td className="py-2 px-3 text-right text-white/70">
                                {r.p_value == null ? "—" : Number(r.p_value).toFixed(4)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="text-white/60 text-sm">Không có kết quả chi tiết.</div>
                  )}
                </>
              )}
            </div>
          ) : (
            <div className="text-white/50 text-sm">Chưa chạy.</div>
          )}
        </GlassCard>
      </div>

      <details className="glass-card rounded-2xl p-5">
        <summary className="cursor-pointer text-white font-semibold">Tình trạng dữ liệu (ẩn/hiện)</summary>
        <div className="mt-4 space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="glass-input px-4 py-2 rounded-lg text-white text-sm" />
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="glass-input px-4 py-2 rounded-lg text-white text-sm" />
            <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" onClick={() => refreshCatalog()}>
              Refresh coverage
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px]">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Series</th>
                  <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Obs</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">From</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">To</th>
                </tr>
              </thead>
              <tbody>
                {series.map((s) => {
                  const c = coverageMap[s.id];
                  const label = seriesOptionLabel(s);
                  return (
                    <tr key={s.id} className="border-b border-white/5 hover:bg-white/5">
                      <td className="py-2 px-3 text-white/80">
                        {label} <span className="text-white/40">({s.id})</span>
                      </td>
                      <td className="py-2 px-3 text-right text-white/90">{c?.n_obs ?? 0}</td>
                      <td className="py-2 px-3 text-white/60">{c?.start || "—"}</td>
                      <td className="py-2 px-3 text-white/60">{c?.end || "—"}</td>
                    </tr>
                  );
                })}
                {series.length === 0 ? (
                  <tr>
                    <td className="py-6 px-3 text-white/60" colSpan={4}>
                      Chưa có catalog series.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div className="text-white/40 text-xs">
            Gợi ý: khi IB/Policy chưa đủ lịch sử, lead‑lag vẫn chạy được với các chuỗi lợi suất/đấu thầu/thứ cấp. Khi dữ liệu tích lũy đủ, các chuỗi sẽ tự “đủ điều kiện” mà không cần làm lại UI.
          </div>
        </div>
      </details>

      <Modal open={helpOpen} title="Giải thích: cách đọc “Ai dẫn ai?”" onClose={() => setHelpOpen(false)}>
        <div className="space-y-4 text-sm">
          <div className="text-white/70">
            Mục tiêu: chuyển “số” → “thông tin”. Đây là mô tả thống kê (precedence), không khẳng định nhân quả và không phải khuyến nghị tài chính.
          </div>

          <div className="glass-card rounded-xl p-4">
            <div className="text-white/90 font-semibold">Các khái niệm chính</div>
            <div className="mt-2 space-y-2 text-white/70">
              <div>• Độ trễ (lag): nếu “X đi trước Y ~k phiên” nghĩa là X thường xuất hiện/biến động sớm hơn Y khoảng k phiên.</div>
              <div>• So theo thay đổi (Δ): so sánh biến động theo thời gian thay vì mức tuyệt đối; thường ổn định hơn khi chuỗi có xu hướng.</div>
              <div>• Cùng chiều / ngược chiều: corr dương/âm cho biết X và Y thường tăng-giảm cùng nhau hay ngược nhau.</div>
              <div>• Tin cậy: tổng hợp từ số cặp quan sát (n_pairs), mức ổn định (stability) và p_adj (nếu có).</div>
            </div>
          </div>

          <div className="glass-card rounded-xl p-4">
            <div className="text-white/90 font-semibold">Vì sao có “p_adj”?</div>
            <div className="mt-2 text-white/70">
              Khi quét nhiều mức lag (và/hoặc thử nhiều cặp X/Y), xác suất “ra kết quả đẹp do may mắn” tăng. p_adj là p-value đã hiệu chỉnh để giảm rủi ro đó.
            </div>
          </div>

          <div className="text-white/50 text-xs">
            Gợi ý: bắt đầu với “Bắt đầu nhanh” (preset). Khi quen rồi hãy chuyển “Nâng cao” để tự chọn X/Y.
          </div>
        </div>
      </Modal>
    </div>
  );
}
