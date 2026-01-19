import Link from "next/link";
import { GlassCard } from "@/components/GlassCard";
import { ManualIngestButton } from "@/components/ManualIngestButton";
import { DashboardMetrics, InsightsPayload, InterbankCompareResponse } from "@/lib/bondlabApi";

function fmtPct(value?: number | null) {
  if (value == null) return "—";
  return `${value.toFixed(2)}%`;
}

function fmtBpsFromPctDiff(value?: number | null) {
  if (value == null) return "—";
  return `${(value * 100).toFixed(0)} bps`;
}

function fmtBps(value?: number | null) {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(0)} bps`;
}

function fmtDateTime(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

function freshnessLine(
  metrics: DashboardMetrics | null,
  key: string
): { text: string; detail?: string } | null {
  const item = metrics?.freshness?.[key];
  if (!item) return null;
  const gap = item.gap_days;
  const used = item.used_date;
  if (gap == null || used == null) return null;
  if (gap <= 0) return null;
  return {
    text: `Dữ liệu hôm nay chưa có; đang hiển thị ${used} (trễ ${gap} ngày).`,
    detail: item.note || undefined,
  };
}

function fmtPts(value?: number | null) {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}`;
}

function horizonLabel(key: "short" | "mid" | "long") {
  if (key === "short") return "Ngắn hạn";
  if (key === "mid") return "Trung hạn";
  return "Dài hạn";
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export default async function Home() {
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8001";

  let error: string | null = null;
  let metrics: DashboardMetrics | null = null;
  let ibCompare: InterbankCompareResponse | null = null;
  let insights: InsightsPayload | null = null;

  try {
    [metrics, ibCompare, insights] = await Promise.all([
      fetchJson<DashboardMetrics>(`${backendUrl}/api/dashboard/metrics`),
      fetchJson<InterbankCompareResponse>(`${backendUrl}/api/interbank/compare`),
      fetchJson<InsightsPayload>(`${backendUrl}/api/insights/horizons`),
    ]);
  } catch (e: any) {
    error = e?.message || "Không thể kết nối backend";
  }

  const onRow = ibCompare?.rows?.find((r) => r.tenor_label === "ON") || null;
  const horizonSummaries: Array<{ key: "short" | "mid" | "long"; text: string }> = (["short", "mid", "long"] as const).map((key) => {
    const h = insights?.horizons?.[key];
    return { key, text: h?.conclusion || "Chưa đủ dữ liệu để đánh giá." };
  });
  const yieldFresh = freshnessLine(metrics, "yield_curve");
  const bankDepositFresh = freshnessLine(metrics, "bank_deposit");
  const bankLoanFresh = freshnessLine(metrics, "bank_loan");
  const stressFresh = freshnessLine(metrics, "stress");

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-bold text-white">Dashboard</h1>
            <p className="text-white/60 mt-2">Tổng quan nhanh. Các tab nghiên cứu chi tiết nằm trong Admin.</p>
          </div>
          <ManualIngestButton />
        </div>
      </div>

      {error ? (
        <GlassCard>
          <div className="text-red-300 text-sm">{error}</div>
          <div className="text-white/40 text-xs mt-1">
            Kiểm tra backend `http://127.0.0.1:8001` (hoặc chạy lại `./scripts/run_local_all.sh`).
          </div>
        </GlassCard>
      ) : null}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <GlassCard>
          <div className="text-white/60 text-sm mb-2">Nhận định</div>
          <div className="text-white font-semibold">3 thời hạn (ngắn / trung / dài)</div>
          <div className="mt-3 space-y-2 text-sm">
            {horizonSummaries.map((x) => (
              <div key={x.key} className="flex items-start gap-3">
                <div className="w-[86px] shrink-0 text-white/60">{horizonLabel(x.key)}</div>
                <div className="text-white/80">{x.text}</div>
              </div>
            ))}
          </div>
          <Link
            className="glass-button px-4 py-2 rounded-lg inline-block text-sm text-white/90 hover:text-white mt-4"
            href="/nhan-dinh"
          >
            Mở Nhận định →
          </Link>
        </GlassCard>

        <GlassCard>
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-white/60 text-sm mb-2">Stress</div>
              <div className="text-white font-semibold">BondY Stress Index</div>
              <div className="text-white/50 text-sm mt-1">
                Ngày: <span className="text-white/70">{metrics?.stress_date || "—"}</span>
              </div>
              {stressFresh ? (
                <div className="text-white/50 text-xs mt-1" title={stressFresh.detail || ""}>
                  {stressFresh.text}
                </div>
              ) : null}
            </div>
            <div className="text-right">
              <div className="text-white text-2xl font-semibold">
                {metrics?.stress_index != null ? metrics.stress_index.toFixed(1) : "—"}
              </div>
              <div className="text-white/60 text-sm">
                Bucket: <span className="text-white/80">{metrics?.stress_bucket || "—"}</span>
                {metrics?.stress_change != null ? (
                  <>
                    {" • "}
                    Δ <span className="text-white/80 font-semibold">{fmtPts(metrics.stress_change)}</span>
                  </>
                ) : null}
              </div>
            </div>
          </div>
          <div className="text-white/60 text-sm mt-3">
            Chi tiết:{" "}
            <Link className="text-white/90 hover:text-white underline" href="/stress">
              Mở Stress →
            </Link>
          </div>
        </GlassCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-white font-semibold">Yield (HNX)</div>
              <div className="text-white/50 text-sm">
                Ngày dữ liệu: <span className="text-white/70">{metrics?.latest_date || "—"}</span>
              </div>
              {yieldFresh ? (
                <div className="text-white/50 text-xs mt-1" title={yieldFresh.detail || ""}>
                  {yieldFresh.text}
                </div>
              ) : null}
            </div>
            <span className="text-white/50 text-xs">2Y/5Y/10Y</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="glass-card rounded-xl p-3">
              <div className="text-white/50 text-xs">2Y</div>
              <div className="text-white font-semibold">{fmtPct(metrics?.two_y)}</div>
              <div className="text-white/50 text-xs mt-1">Δ {fmtBps(metrics?.two_y_change_bps)}</div>
            </div>
            <div className="glass-card rounded-xl p-3">
              <div className="text-white/50 text-xs">5Y</div>
              <div className="text-white font-semibold">{fmtPct(metrics?.five_y)}</div>
              <div className="text-white/50 text-xs mt-1">Δ {fmtBps(metrics?.five_y_change_bps)}</div>
            </div>
            <div className="glass-card rounded-xl p-3">
              <div className="text-white/50 text-xs">10Y</div>
              <div className="text-white font-semibold">{fmtPct(metrics?.ten_y)}</div>
              <div className="text-white/50 text-xs mt-1">Δ {fmtBps(metrics?.ten_y_change_bps)}</div>
            </div>
          </div>
          <div className="text-white/60 text-sm">
            Spread 10Y–2Y:{" "}
            <span className="text-white/80 font-semibold">
              {fmtBpsFromPctDiff(metrics?.spread_10y_2y)}
            </span>
            {metrics?.spread_10y_2y_change_bps != null ? (
              <>
                {" • "}
                Δ <span className="text-white/80 font-semibold">{fmtBps(metrics.spread_10y_2y_change_bps)}</span>
              </>
            ) : null}
          </div>
        </GlassCard>

        <GlassCard className="space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-white font-semibold">Interbank (SBV)</div>
              <div className="text-white/50 text-sm">
                Ngày áp dụng: <span className="text-white/70">{ibCompare?.today_date || "—"}</span>
                <span
                  className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-white/10 text-[10px] text-white/70"
                  title="SBV công bố ‘ngày áp dụng’ (ngày có hiệu lực). Ngày này có thể không đổi dù hệ thống vừa crawl lại. ‘Cập nhật’ là thời điểm fetch."
                  aria-label="Giải thích Ngày áp dụng vs Cập nhật"
                >
                  i
                </span>
                {" • "}
                Kỳ trước: <span className="text-white/70">{ibCompare?.prev_date || "—"}</span>
                {ibCompare?.today_fetched_at ? (
                  <>
                    {" • "}
                    Cập nhật: <span className="text-white/70">{fmtDateTime(ibCompare.today_fetched_at)}</span>
                  </>
                ) : null}
              </div>
              {ibCompare?.today_gap_days != null && ibCompare.today_gap_days > 0 ? (
                <div className="text-white/50 text-xs mt-1" title={ibCompare.note || ""}>
                  SBV chưa công bố “ngày áp dụng” mới; đang hiển thị ngày gần nhất (trễ {ibCompare.today_gap_days} ngày).
                </div>
              ) : null}
            </div>
          </div>
          <div className="glass-card rounded-xl p-3">
            <div className="text-white/50 text-xs">ON</div>
            <div className="text-white font-semibold">{fmtPct(metrics?.on_rate)}</div>
            <div className="text-white/50 text-xs mt-1">Δ {fmtBps(onRow?.change_bps ?? null)}</div>
          </div>
          {onRow?.change_bps != null && Math.abs(onRow.change_bps) >= 25 ? (
            <div className="text-white/70 text-sm">
              Tín hiệu: O/N biến động mạnh ({fmtBps(onRow.change_bps)}).
            </div>
          ) : null}
          <div className="text-white/60 text-sm">
            Bảng đầy đủ:{" "}
            <Link className="text-white/90 hover:text-white underline" href="/interbank">
              Mở Interbank →
            </Link>
          </div>
        </GlassCard>

        <GlassCard className="space-y-3">
          <div className="text-white font-semibold">Lãi suất ngân hàng (TB)</div>
          <div className="grid grid-cols-1 gap-2">
            <div className="glass-card rounded-xl p-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-white/60 text-sm">Tiền gửi TB (12T)</div>
                <div className="text-white/40 text-xs mt-1">
                  Ngày: <span className="text-white/60">{metrics?.bank_deposit_date || "—"}</span>
                  {metrics?.bank_deposit_prev_date ? (
                    <>
                      {" • "}
                      Δ <span className="text-white/70">{fmtBps(metrics.deposit_change_bps)}</span>
                    </>
                  ) : null}
                </div>
              </div>
              <div className="text-white font-semibold">{fmtPct(metrics?.deposit_avg_12m)}</div>
            </div>
            <div className="glass-card rounded-xl p-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-white/60 text-sm">Cho vay TB</div>
                <div className="text-white/40 text-xs mt-1">
                  Ngày: <span className="text-white/60">{metrics?.bank_loan_date || "—"}</span>
                  {metrics?.bank_loan_prev_date ? (
                    <>
                      {" • "}
                      Δ <span className="text-white/70">{fmtBps(metrics.loan_change_bps)}</span>
                    </>
                  ) : null}
                </div>
              </div>
              <div className="text-white font-semibold">{fmtPct(metrics?.loan_avg)}</div>
            </div>
          </div>
          {bankDepositFresh ? (
            <div className="text-white/50 text-xs" title={bankDepositFresh.detail || ""}>
              {bankDepositFresh.text}
            </div>
          ) : null}
          {bankLoanFresh ? (
            <div className="text-white/50 text-xs" title={bankLoanFresh.detail || ""}>
              {bankLoanFresh.text}
            </div>
          ) : null}
          <div className="text-white/60 text-sm">
            Chi tiết:{" "}
            <Link className="text-white/90 hover:text-white underline" href="/lai-suat">
              Mở Lãi suất →
            </Link>
          </div>
        </GlassCard>
      </div>

      {ibCompare?.rows?.length ? (
        <GlassCard className="space-y-3">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <div className="text-white font-semibold">Interbank snapshot (hôm nay vs hôm qua)</div>
              <div className="text-white/50 text-sm">
                Hiển thị các kỳ có dữ liệu. Nếu thiếu kỳ (ví dụ 9M), hệ thống sẽ tự đầy khi SBV công bố.
              </div>
            </div>
            <Link className="text-white/80 hover:text-white text-sm underline" href="/interbank">
              Xem chi tiết →
            </Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px]">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Kỳ</th>
                  <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Hôm nay</th>
                  <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Hôm qua</th>
                  <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Δ</th>
                </tr>
              </thead>
              <tbody>
                {ibCompare.rows.map((r) => (
                  <tr key={r.tenor_label} className="border-b border-white/5 hover:bg-white/5">
                    <td className="py-2 px-3 text-white">{r.tenor_label}</td>
                    <td className="py-2 px-3 text-right text-white/90">{fmtPct(r.today_rate)}</td>
                    <td className="py-2 px-3 text-right text-white/60">{fmtPct(r.prev_rate)}</td>
                    <td className="py-2 px-3 text-right text-white/90 font-semibold">{fmtBps(r.change_bps)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      ) : null}
    </div>
  );
}
