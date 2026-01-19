"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import { bondlabApi, IngestRunRecord } from "@/lib/bondlabApi";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: "GET", headers: { "Content-Type": "application/json" } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

async function postJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" } });
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

type ProviderStatusResponse = {
  status: string;
  probe_timestamp?: string;
  message?: string;
  providers?: Record<
    string,
    {
      fetch_latest: boolean;
      fetch_historical: boolean;
      backfill_supported: boolean;
      earliest_success_date?: string | null;
      latest_success_date?: string | null;
      failure_modes?: string[];
    }
  >;
};

export default function AdminIngestPage() {
  const [runs, setRuns] = useState<IngestRunRecord[]>([]);
  const [providerStatus, setProviderStatus] = useState<ProviderStatusResponse | null>(null);
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [providersCsv, setProvidersCsv] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    setErr(null);
    const [r, p] = await Promise.all([
      bondlabApi.ingestRuns(50),
      fetchJson<ProviderStatusResponse>("/api/admin/provider-status"),
    ]);
    setRuns(r);
    setProviderStatus(p);
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e?.message || "Không thể tải dữ liệu"));
  }, []);

  const providerRows = useMemo(() => {
    const providers = providerStatus?.providers || {};
    return Object.entries(providers).map(([name, info]) => ({ name, ...info }));
  }, [providerStatus]);

  async function runDaily() {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>("/api/admin/ingest/daily");
      setMsg(`Đã chạy ingest daily: ${res?.status || "ok"}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Chạy ingest daily thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function runProbe() {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>("/api/admin/ingest/probe");
      setMsg(`Đã probe providers: ${res?.status || "ok"}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Probe thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function runBackfill() {
    try {
      if (!startDate || !endDate) {
        setErr("Vui lòng chọn start/end date");
        return;
      }
      setBusy(true);
      setMsg(null);
      setErr(null);
      const sp = new URLSearchParams();
      sp.append("start_date", startDate);
      sp.append("end_date", endDate);
      const providers = providersCsv
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      for (const p of providers) sp.append("providers", p);
      const res = await postJson<any>(`/api/admin/ingest/backfill?${sp.toString()}`);
      setMsg(`Đã chạy backfill: ${res?.status || "ok"}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Backfill thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Admin • Ingest</h1>
          <p className="text-white/60 mt-2">Chạy pipeline ingest/backfill và theo dõi trạng thái provider.</p>
        </div>
        <Link className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" href="/admin">
          ← Admin
        </Link>
      </div>

      {(msg || err) && (
        <GlassCard>
          {msg && <div className="text-emerald-200 text-sm">{msg}</div>}
          {err && <div className="text-red-300 text-sm">{err}</div>}
        </GlassCard>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <GlassCard className="space-y-3">
          <div className="text-white font-semibold">Hành động</div>
          <div className="flex flex-wrap gap-2">
            <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50" disabled={busy} onClick={() => runDaily()}>
              Chạy ingest daily
            </button>
            <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50" disabled={busy} onClick={() => runProbe()}>
              Probe providers
            </button>
            <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50" disabled={busy} onClick={() => refresh()}>
              Refresh
            </button>
          </div>
          <div className="text-white/50 text-sm">
            Daily ingest cập nhật dữ liệu mới nhất. Backfill chỉ nên dùng khi cần nạp lịch sử.
          </div>
        </GlassCard>

        <GlassCard className="space-y-3">
          <div className="text-white font-semibold">Backfill</div>
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
            <input
              value={providersCsv}
              onChange={(e) => setProvidersCsv(e.target.value)}
              placeholder="providers (csv) e.g. HNX_YC,HNX_TRADING"
              className="glass-input px-4 py-2 rounded-lg text-white text-sm flex-1 min-w-[220px]"
            />
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              disabled={busy || !startDate || !endDate}
              onClick={() => runBackfill()}
            >
              Chạy backfill
            </button>
          </div>
          <div className="text-white/50 text-sm">
            Nếu để trống providers: backend sẽ tự chọn default. Data VN đôi lúc thiếu phiên; backfill có thể chạy lâu.
          </div>
        </GlassCard>
      </div>

      <GlassCard className="space-y-3">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="text-white font-semibold">Provider status</div>
            <div className="text-white/50 text-sm">
              {providerStatus?.status === "ok"
                ? `Probe: ${providerStatus?.probe_timestamp || "—"}`
                : providerStatus?.message || "Chưa có probe"}
            </div>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px]">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Provider</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Latest</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Historical</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Backfill</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Earliest</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Latest OK</th>
              </tr>
            </thead>
            <tbody>
              {providerRows.map((p) => (
                <tr key={p.name} className="border-b border-white/5 hover:bg-white/5">
                  <td className="py-2 px-3 text-white">{p.name}</td>
                  <td className="py-2 px-3 text-white/70">{p.fetch_latest ? "YES" : "NO"}</td>
                  <td className="py-2 px-3 text-white/70">{p.fetch_historical ? "YES" : "NO"}</td>
                  <td className="py-2 px-3 text-white/70">{p.backfill_supported ? "YES" : "NO"}</td>
                  <td className="py-2 px-3 text-white/60">{fmtDate(p.earliest_success_date)}</td>
                  <td className="py-2 px-3 text-white/60">{fmtDate(p.latest_success_date)}</td>
                </tr>
              ))}
              {providerRows.length === 0 ? (
                <tr>
                  <td className="py-6 px-3 text-white/60" colSpan={6}>
                    Chưa có dữ liệu probe. Bấm “Probe providers”.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </GlassCard>

      <GlassCard className="space-y-3">
        <div className="text-white font-semibold">Ingest runs (gần đây)</div>
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

