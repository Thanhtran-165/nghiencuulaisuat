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

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

export default function AdminQualityPage() {
  const [targetDate, setTargetDate] = useState(isoDate(new Date()));
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [latest, setLatest] = useState<any>(null);
  const [results, setResults] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    setErr(null);
    const [l, r] = await Promise.all([
      fetchJson<any>(`/api/admin/quality/latest?date=${encodeURIComponent(targetDate)}`),
      fetchJson<any[]>(`/api/admin/quality/results?date=${encodeURIComponent(targetDate)}`),
    ]);
    setLatest(l);
    setResults(r);
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e?.message || "Không thể tải DQ"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runOne() {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>(`/api/admin/quality/run?date=${encodeURIComponent(targetDate)}`);
      setMsg(`DQ run: ${res?.status || "ok"}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "DQ run thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function runRange() {
    try {
      if (!startDate || !endDate) {
        setErr("Vui lòng chọn start/end date");
        return;
      }
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>(
        `/api/admin/quality/run-range?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`
      );
      setMsg(`DQ run-range: processed=${res?.processed || "—"} ok=${res?.succeeded || "—"} failed=${res?.failed || "—"}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "DQ run-range thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Admin • Quality</h1>
          <p className="text-white/60 mt-2">Data Quality checks (nhằm phát hiện thiếu dữ liệu, drift, outliers).</p>
        </div>
        <Link className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" href="/admin">
          ← Admin
        </Link>
      </div>

      {(msg || err) && (
        <GlassCard>
          {msg && <div className="text-emerald-200 text-sm break-words">{msg}</div>}
          {err && <div className="text-red-300 text-sm">{err}</div>}
        </GlassCard>
      )}

      <GlassCard className="space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-white/60 text-sm">Target date</span>
          <input
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            className="glass-input px-4 py-2 rounded-lg text-white text-sm"
          />
          <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" onClick={() => refresh()}>
            Refresh
          </button>
          <button
            className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
            disabled={busy}
            onClick={() => runOne()}
          >
            Run DQ (1 ngày)
          </button>
        </div>

        <div className="text-white/50 text-sm">
          Latest status: <span className="text-white/80">{latest?.status || "—"}</span>{" "}
          {latest?.message ? <span className="text-white/50">• {latest.message}</span> : null}
        </div>
        <pre className="text-white/70 text-xs whitespace-pre-wrap break-words">{JSON.stringify(latest, null, 2)}</pre>
      </GlassCard>

      <GlassCard className="space-y-3">
        <div className="text-white font-semibold">Results</div>
        <pre className="text-white/70 text-xs whitespace-pre-wrap break-words">{JSON.stringify(results || [], null, 2)}</pre>
      </GlassCard>

      <GlassCard className="space-y-3">
        <div className="text-white font-semibold">Run range</div>
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
          <button
            className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
            disabled={busy || !startDate || !endDate}
            onClick={() => runRange()}
          >
            Run DQ range
          </button>
        </div>
      </GlassCard>
    </div>
  );
}

