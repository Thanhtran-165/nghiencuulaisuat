"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { GlassCard } from "@/components/GlassCard";

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

export default function AdminLaiSuatPage() {
  const [status, setStatus] = useState<any>(null);
  const [log, setLog] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    setErr(null);
    const [s, l] = await Promise.all([
      fetchJson<any>("/api/admin/lai-suat/status"),
      fetchJson<any>("/api/admin/lai-suat/log-tail?lines=200"),
    ]);
    setStatus(s);
    setLog(l);
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e?.message || "Không thể tải status"));
  }, []);

  async function updateToday() {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>("/api/admin/lai-suat/update-today");
      setMsg(`Đã update: date=${res?.date || "—"} rows=${res?.rows_inserted || 0}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Update thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function syncMissing() {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>("/api/admin/lai-suat/sync-missing");
      setMsg(`Đã sync missing: ${res?.status || "ok"}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Sync missing thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function scrapeOnly() {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>("/api/admin/lai-suat/scrape");
      setMsg(`Đã scrape (SQLite): exit=${res?.exit_code}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Scrape thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Admin • Lãi suất (Lai_suat)</h1>
          <p className="text-white/60 mt-2">Quản lý scrape + đồng bộ DB (SQLite → DuckDB: bank_rates).</p>
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

      {(msg || err) && (
        <GlassCard>
          {msg && <div className="text-emerald-200 text-sm break-words">{msg}</div>}
          {err && <div className="text-red-300 text-sm">{err}</div>}
        </GlassCard>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <GlassCard className="space-y-3">
          <div className="text-white font-semibold">Hành động</div>
          <div className="flex flex-wrap gap-2">
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              disabled={busy}
              onClick={() => updateToday()}
            >
              Update hôm nay (scrape + sync)
            </button>
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              disabled={busy}
              onClick={() => scrapeOnly()}
            >
              Chỉ scrape (SQLite)
            </button>
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              disabled={busy}
              onClick={() => syncMissing()}
            >
              Sync missing (DuckDB)
            </button>
          </div>
          <div className="text-white/50 text-sm">
            Nếu nguồn chưa phát sinh kỳ mới, “Update hôm nay” vẫn chạy nhưng max_date có thể giữ nguyên.
          </div>
        </GlassCard>

        <GlassCard className="space-y-3">
          <div className="text-white font-semibold">Status</div>
          <pre className="text-white/70 text-xs whitespace-pre-wrap break-words">{JSON.stringify(status, null, 2)}</pre>
        </GlassCard>
      </div>

      <GlassCard className="space-y-3">
        <div className="text-white font-semibold">Log tail</div>
        <div className="text-white/50 text-sm">{log?.path || ""}</div>
        <pre className="text-white/70 text-xs whitespace-pre-wrap break-words">{log?.tail || ""}</pre>
      </GlassCard>
    </div>
  );
}

