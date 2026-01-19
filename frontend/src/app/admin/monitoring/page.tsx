"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: "GET", headers: { "Content-Type": "application/json" } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export default function AdminMonitoringPage() {
  const [summary, setSummary] = useState<any>(null);
  const [providers, setProviders] = useState<any>(null);
  const [drift, setDrift] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    setErr(null);
    const [s, p, d] = await Promise.all([
      fetchJson<any>("/api/admin/monitoring/summary"),
      fetchJson<any>("/api/admin/monitoring/providers"),
      fetchJson<any>("/api/admin/monitoring/drift"),
    ]);
    setSummary(s);
    setProviders(p);
    setDrift(d);
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e?.message || "Không thể tải monitoring"));
  }, []);

  const providerRows = useMemo(() => {
    const p = providers?.providers || {};
    return Object.entries(p).map(([name, info]) => ({ name, ...(info as any) }));
  }, [providers]);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Admin • Monitoring</h1>
          <p className="text-white/60 mt-2">Theo dõi sức khỏe pipeline (SLO, reliability, drift).</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" onClick={() => refresh()}>
            Refresh
          </button>
          <Link className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" href="/admin">
            ← Admin
          </Link>
        </div>
      </div>

      {err && (
        <GlassCard>
          <div className="text-red-300 text-sm">{err}</div>
        </GlassCard>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Last ingest</div>
          <div className="text-white font-semibold">{summary?.last_ingest?.provider || "—"}</div>
          <div className="text-white/40 text-xs">
            {summary?.last_ingest?.status || "—"} • {summary?.last_ingest?.started_at || "—"}
          </div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Last DQ</div>
          <div className="text-white font-semibold">{summary?.last_dq?.status || "—"}</div>
          <div className="text-white/40 text-xs">
            {summary?.last_dq?.run_at || "—"} • target {summary?.last_dq?.target_date || "—"}
          </div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">SLO (30d)</div>
          <div className="text-white font-semibold">
            DQ success: {summary?.slo_30d?.dq_success_rate == null ? "—" : `${summary.slo_30d.dq_success_rate}%`}
          </div>
          <div className="text-white/40 text-xs">
            Snapshot coverage: {summary?.slo_30d?.snapshot_coverage == null ? "—" : `${summary.slo_30d.snapshot_coverage}%`}
          </div>
        </GlassCard>
      </div>

      <GlassCard className="space-y-3">
        <div className="text-white font-semibold">Providers reliability (30d)</div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px]">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Provider</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Total</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Success</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Error</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Success rate</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Avg duration (s)</th>
              </tr>
            </thead>
            <tbody>
              {providerRows.map((p: any) => (
                <tr key={p.name} className="border-b border-white/5 hover:bg-white/5">
                  <td className="py-2 px-3 text-white/90">{p.name}</td>
                  <td className="py-2 px-3 text-right text-white/70">{p.total ?? "—"}</td>
                  <td className="py-2 px-3 text-right text-white/70">{p.success ?? "—"}</td>
                  <td className="py-2 px-3 text-right text-white/70">{p.error ?? "—"}</td>
                  <td className="py-2 px-3 text-right text-white/90 font-semibold">
                    {p.success_rate == null ? "—" : `${p.success_rate}%`}
                  </td>
                  <td className="py-2 px-3 text-right text-white/60">{providers?.latencies?.[p.name] ?? "—"}</td>
                </tr>
              ))}
              {providerRows.length === 0 ? (
                <tr>
                  <td className="py-6 px-3 text-white/60" colSpan={6}>
                    Chưa có dữ liệu.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </GlassCard>

      <GlassCard className="space-y-3">
        <div className="text-white font-semibold">Drift signals (30d)</div>
        <div className="text-white/50 text-sm">
          Nếu provider thay đổi fingerprint nhiều lần hoặc parse_failures tăng, có thể trang nguồn đã đổi cấu trúc.
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px]">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Provider</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Dataset</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Changes</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Last fetched</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Avg rows</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Parse fails</th>
              </tr>
            </thead>
            <tbody>
              {(drift?.drifts || []).map((d: any, idx: number) => (
                <tr key={`${d.provider}-${d.dataset_id}-${idx}`} className="border-b border-white/5 hover:bg-white/5">
                  <td className="py-2 px-3 text-white/80">{d.provider}</td>
                  <td className="py-2 px-3 text-white/80">{d.dataset_id}</td>
                  <td className="py-2 px-3 text-right text-white/90 font-semibold">{d.fingerprint_changes}</td>
                  <td className="py-2 px-3 text-white/60">{d.last_fetched}</td>
                  <td className="py-2 px-3 text-right text-white/60">{d.avg_rowcount ?? "—"}</td>
                  <td className="py-2 px-3 text-right text-red-300">{d.parse_failures ?? 0}</td>
                </tr>
              ))}
              {(drift?.drifts || []).length === 0 ? (
                <tr>
                  <td className="py-6 px-3 text-white/60" colSpan={6}>
                    Chưa thấy drift.
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

