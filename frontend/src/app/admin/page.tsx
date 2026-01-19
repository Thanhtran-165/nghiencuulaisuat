"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import { bondlabApi, CoverageSummary, IngestRunRecord } from "@/lib/bondlabApi";

async function postJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function fmtDate(value?: string | null) {
  if (!value) return "—";
  return value;
}

export default function AdminPage() {
  const [runs, setRuns] = useState<IngestRunRecord[]>([]);
  const [coverage, setCoverage] = useState<CoverageSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    const [r, c] = await Promise.all([bondlabApi.ingestRuns(50), bondlabApi.coverage()]);
    setRuns(r);
    setCoverage(c);
  }

  useEffect(() => {
    refresh().catch((e) => setError(e?.message || "Không thể tải dữ liệu"));
  }, []);

  const coverageRows = useMemo(() => {
    if (!coverage) return [];
    return Object.entries(coverage).map(([k, v]) => ({ table: k, ...v }));
  }, [coverage]);

  async function runDaily() {
    try {
      setLoading(true);
      setActionMsg(null);
      setError(null);
      const res = await postJson<any>("/api/admin/ingest/daily");
      setActionMsg(`Đã chạy ingest daily: ${res?.status || "ok"}`);
      await refresh();
    } catch (e: any) {
      setError(e?.message || "Chạy ingest daily thất bại");
    } finally {
      setLoading(false);
    }
  }

  async function syncLaiSuatMissing() {
    try {
      setLoading(true);
      setActionMsg(null);
      setError(null);
      const res = await postJson<any>("/api/admin/lai-suat/sync-missing");
      setActionMsg(`Đã sync lãi suất (missing): ${res?.status || "ok"}`);
      await refresh();
    } catch (e: any) {
      setError(e?.message || "Sync lãi suất thất bại");
    } finally {
      setLoading(false);
    }
  }

  async function updateLaiSuatToday() {
    try {
      setLoading(true);
      setActionMsg(null);
      setError(null);
      const res = await postJson<any>("/api/admin/lai-suat/update-today");
      setActionMsg(`Đã cập nhật lãi suất hôm nay: ${res?.status || "ok"}`);
      await refresh();
    } catch (e: any) {
      setError(e?.message || "Cập nhật lãi suất hôm nay thất bại");
    } finally {
      setLoading(false);
    }
  }

  async function runProbe() {
    try {
      setLoading(true);
      setActionMsg(null);
      setError(null);
      const res = await postJson<any>("/api/admin/ingest/probe");
      setActionMsg(`Đã probe providers: ${res?.status || "ok"}`);
      await refresh();
    } catch (e: any) {
      setError(e?.message || "Probe thất bại");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">Admin</h1>
        <p className="text-white/60 mt-2">Công cụ vận hành & theo dõi dữ liệu. Không dùng UI cũ nữa.</p>
      </div>

      {(actionMsg || error) && (
        <GlassCard>
          {actionMsg && <div className="text-emerald-200 text-sm">{actionMsg}</div>}
          {error && <div className="text-red-300 text-sm">{error}</div>}
        </GlassCard>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <GlassCard>
          <div className="text-white/60 text-sm mb-2">Ingest</div>
          <div className="text-white font-semibold mb-2">Chạy pipeline & probe</div>
          <Link className="text-white/90 hover:text-white underline text-sm" href="/admin/ingest">
            Mở Ingest →
          </Link>
        </GlassCard>
        <GlassCard>
          <div className="text-white/60 text-sm mb-2">Alerts</div>
          <div className="text-white font-semibold mb-2">Thresholds & test</div>
          <Link className="text-white/90 hover:text-white underline text-sm" href="/admin/alerts">
            Mở Alerts →
          </Link>
        </GlassCard>
        <GlassCard>
          <div className="text-white/60 text-sm mb-2">Monitoring</div>
          <div className="text-white font-semibold mb-2">SLO & drift</div>
          <Link className="text-white/90 hover:text-white underline text-sm" href="/admin/monitoring">
            Mở Monitoring →
          </Link>
        </GlassCard>
        <GlassCard>
          <div className="text-white/60 text-sm mb-2">Quality</div>
          <div className="text-white font-semibold mb-2">Data quality checks</div>
          <Link className="text-white/90 hover:text-white underline text-sm" href="/admin/quality">
            Mở Quality →
          </Link>
        </GlassCard>
        <GlassCard>
          <div className="text-white/60 text-sm mb-2">Notifications</div>
          <div className="text-white font-semibold mb-2">Channels & events</div>
          <Link className="text-white/90 hover:text-white underline text-sm" href="/admin/notifications">
            Mở Notifications →
          </Link>
        </GlassCard>
        <GlassCard>
          <div className="text-white/60 text-sm mb-2">Lãi suất</div>
          <div className="text-white font-semibold mb-2">Scrape & sync bank_rates</div>
          <Link className="text-white/90 hover:text-white underline text-sm" href="/admin/lai-suat">
            Mở Lãi suất admin →
          </Link>
        </GlassCard>
        <GlassCard>
          <div className="text-white/60 text-sm mb-2">Ops</div>
          <div className="text-white font-semibold mb-2">Backups</div>
          <Link className="text-white/90 hover:text-white underline text-sm" href="/admin/ops">
            Mở Ops →
          </Link>
        </GlassCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <GlassCard className="space-y-3">
          <div className="text-white font-semibold">Hành động nhanh</div>
          <div className="flex flex-wrap gap-2">
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              onClick={() => runDaily()}
              disabled={loading}
            >
              {loading ? "Đang chạy..." : "Chạy cập nhật daily"}
            </button>
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              onClick={() => updateLaiSuatToday()}
              disabled={loading}
            >
              Cập nhật lãi suất hôm nay
            </button>
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              onClick={() => syncLaiSuatMissing()}
              disabled={loading}
            >
              Sync lãi suất (missing)
            </button>
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              onClick={() => runProbe()}
              disabled={loading}
            >
              Probe providers
            </button>
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              onClick={() => refresh()}
              disabled={loading}
            >
              Refresh
            </button>
          </div>
          <div className="text-white/50 text-sm">
            Gợi ý: “Nhận định” sẽ tự hết trạng thái chờ khi các bảng tích lũy đủ phiên (yield/interbank/policy…).
          </div>
        </GlassCard>

        <GlassCard className="space-y-3">
          <div className="text-white font-semibold">Coverage (DB)</div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px]">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Bảng</th>
                  <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Số ngày</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Từ</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Đến</th>
                </tr>
              </thead>
              <tbody>
                {coverageRows.map((r) => (
                  <tr key={r.table} className="border-b border-white/5 hover:bg-white/5">
                    <td className="py-2 px-3 text-white">{r.table}</td>
                    <td className="py-2 px-3 text-right text-white/90 font-semibold">{r.date_count}</td>
                    <td className="py-2 px-3 text-white/60">{fmtDate(r.earliest_date)}</td>
                    <td className="py-2 px-3 text-white/60">{fmtDate(r.latest_date)}</td>
                  </tr>
                ))}
                {!coverageRows.length ? (
                  <tr>
                    <td className="py-6 px-3 text-white/60" colSpan={4}>
                      Chưa tải được coverage.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </GlassCard>
      </div>

      <GlassCard className="space-y-3">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <div className="text-white font-semibold">Ingest runs (gần đây)</div>
            <div className="text-white/50 text-sm">Theo dõi pipeline chạy hằng ngày và lỗi nếu có.</div>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px]">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Provider</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Range</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Status</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Rows</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Started</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Ended</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Error</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-b border-white/5 hover:bg-white/5">
                  <td className="py-2 px-3 text-white">{r.provider}</td>
                  <td className="py-2 px-3 text-white/60">
                    {fmtDate(r.start_date)} → {fmtDate(r.end_date)}
                  </td>
                  <td className="py-2 px-3 text-white/90 font-semibold">{r.status}</td>
                  <td className="py-2 px-3 text-right text-white/90">{r.rows_inserted}</td>
                  <td className="py-2 px-3 text-white/60">{r.started_at}</td>
                  <td className="py-2 px-3 text-white/60">{r.ended_at || "—"}</td>
                  <td className="py-2 px-3 text-red-300 text-sm">{r.error_message || ""}</td>
                </tr>
              ))}
              {!runs.length ? (
                <tr>
                  <td className="py-6 px-3 text-white/60" colSpan={7}>
                    Chưa có lịch sử ingest.
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
