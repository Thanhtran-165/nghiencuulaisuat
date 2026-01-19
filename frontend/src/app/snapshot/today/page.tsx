"use client";

import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function fmtPct(v?: number | null) {
  if (v == null) return "—";
  return `${v.toFixed(2)}%`;
}

export default function SnapshotTodayPage() {
  const [date, setDate] = useState<string>("");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(target?: string) {
    try {
      setLoading(true);
      setError(null);
      const qs = target ? `?target_date=${encodeURIComponent(target)}` : "";
      const snapshot = await fetchJson<any>(`/api/snapshot/today${qs}`);
      setData(snapshot);
      if (snapshot?.date) setDate(snapshot.date);
    } catch (e: any) {
      setError(e?.message || "Không thể tải snapshot");
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const tomTat = data?.tom_tat || {};
  const dienGiai: string[] = data?.dien_giai || [];
  const watchlist: any[] = data?.watchlist || [];

  const changes = useMemo(() => {
    const c = data?.so_voi_hom_qua?.changes || {};
    return c;
  }, [data]);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Snapshot</h1>
          <p className="text-white/60 mt-2">Tóm tắt hằng ngày (tiếng Việt) từ các chỉ số hiện có.</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="glass-input px-4 py-2 rounded-lg text-white text-sm"
          />
          <button
            className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
            disabled={loading || !date}
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

      {data && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            <GlassCard className="space-y-2">
              <div className="text-white/60 text-sm">Điểm số</div>
              <div className="text-white text-2xl font-bold">{tomTat?.diem_so ?? "—"}</div>
              <div className="text-white/40 text-sm">{tomTat?.mo_ta || ""}</div>
            </GlassCard>
            <GlassCard className="space-y-2">
              <div className="text-white/60 text-sm">10Y</div>
              <div className="text-white text-2xl font-bold">{fmtPct(tomTat?.lai_suat_10y)}</div>
              <div className="text-white/40 text-sm">Lợi suất 10 năm</div>
            </GlassCard>
            <GlassCard className="space-y-2">
              <div className="text-white/60 text-sm">Độ cong (10Y–2Y)</div>
              <div className="text-white text-2xl font-bold">
                {tomTat?.do_cong == null ? "—" : `${(tomTat.do_cong * 100).toFixed(0)} bps`}
              </div>
              <div className="text-white/40 text-sm">Chênh lệch dài–ngắn</div>
            </GlassCard>
            <GlassCard className="space-y-2">
              <div className="text-white/60 text-sm">Interbank O/N</div>
              <div className="text-white text-2xl font-bold">{fmtPct(tomTat?.lai_suat_qua_dem)}</div>
              <div className="text-white/40 text-sm">Áp lực thanh khoản ngắn hạn</div>
            </GlassCard>
          </div>

          <GlassCard className="space-y-3">
            <div className="text-white font-semibold">Diễn giải</div>
            <ul className="list-disc pl-5 text-white/70 space-y-1">
              {dienGiai.map((x, idx) => (
                <li key={idx}>{x}</li>
              ))}
            </ul>
          </GlassCard>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <GlassCard className="space-y-3">
              <div className="text-white font-semibold">So với hôm qua</div>
              <div className="text-white/50 text-sm">
                Baseline: <span className="text-white/70">{data?.baseline_date || "—"}</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px]">
                  <thead>
                    <tr className="border-b border-white/10">
                      <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Chỉ số</th>
                      <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Hiện tại</th>
                      <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Baseline</th>
                      <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Xu hướng</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(changes).map(([k, v]: any) => (
                      <tr key={k} className="border-b border-white/5 hover:bg-white/5">
                        <td className="py-2 px-3 text-white">{k}</td>
                        <td className="py-2 px-3 text-right text-white/90">{v?.hien_tai ?? "—"}</td>
                        <td className="py-2 px-3 text-right text-white/60">{v?.baseline ?? "—"}</td>
                        <td className="py-2 px-3 text-white/80">{v?.xu_huong ?? ""}</td>
                      </tr>
                    ))}
                    {Object.keys(changes).length === 0 ? (
                      <tr>
                        <td className="py-4 px-3 text-white/60" colSpan={4}>
                          Chưa có dữ liệu so sánh.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </GlassCard>

            <GlassCard className="space-y-3">
              <div className="text-white font-semibold">Watchlist</div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px]">
                  <thead>
                    <tr className="border-b border-white/10">
                      <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Loại</th>
                      <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Mức</th>
                      <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Nội dung</th>
                    </tr>
                  </thead>
                  <tbody>
                    {watchlist.map((w, idx) => (
                      <tr key={idx} className="border-b border-white/5 hover:bg-white/5">
                        <td className="py-2 px-3 text-white">{w?.loai}</td>
                        <td className="py-2 px-3 text-white/80 font-semibold">{w?.muc_do}</td>
                        <td className="py-2 px-3 text-white/70">{w?.noi_dung}</td>
                      </tr>
                    ))}
                    {watchlist.length === 0 ? (
                      <tr>
                        <td className="py-4 px-3 text-white/60" colSpan={3}>
                          Không có mục watchlist.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          </div>

          <details className="glass-card rounded-2xl p-6">
            <summary className="cursor-pointer text-white/80 hover:text-white">Xem JSON raw</summary>
            <pre className="mt-3 text-xs text-white/60 whitespace-pre-wrap break-words">
              {JSON.stringify(data, null, 2)}
            </pre>
          </details>
        </>
      )}
    </div>
  );
}

