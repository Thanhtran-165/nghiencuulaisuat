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

async function postJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

type AlertThreshold = {
  alert_code: string;
  enabled: boolean;
  severity: string;
  params: Record<string, any>;
  updated_at?: string | null;
};

export default function AdminAlertsPage() {
  const [thresholds, setThresholds] = useState<AlertThreshold[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [enabled, setEnabled] = useState(true);
  const [severity, setSeverity] = useState("MEDIUM");
  const [paramsJson, setParamsJson] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    setErr(null);
    const t = await fetchJson<AlertThreshold[]>("/api/admin/alerts");
    setThresholds(t);
    if (!selected && t[0]?.alert_code) setSelected(t[0].alert_code);
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e?.message || "Không thể tải thresholds"));
  }, []);

  const selectedRow = useMemo(
    () => thresholds.find((t) => t.alert_code === selected) || null,
    [thresholds, selected]
  );

  useEffect(() => {
    if (!selectedRow) return;
    setEnabled(selectedRow.enabled);
    setSeverity(selectedRow.severity);
    setParamsJson(JSON.stringify(selectedRow.params || {}, null, 2));
  }, [selectedRow]);

  async function save() {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      JSON.parse(paramsJson || "{}");
      const sp = new URLSearchParams();
      sp.append("enabled", String(enabled));
      sp.append("severity", severity);
      sp.append("params", paramsJson || "{}");
      const res = await postJson<any>(`/api/admin/alerts/${encodeURIComponent(selected)}?${sp.toString()}`);
      setMsg(`Đã lưu: ${res.alert_code}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Lưu thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function reload() {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>("/api/admin/alerts/reload");
      setMsg(res?.message || "Reloaded");
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Reload thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const sp = new URLSearchParams();
      sp.append("alert_code", selected);
      const res = await postJson<any>(`/api/admin/alerts/test?${sp.toString()}`);
      setMsg(`Test result: ${JSON.stringify(res)}`);
    } catch (e: any) {
      setErr(e?.message || "Test thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Admin • Alerts</h1>
          <p className="text-white/60 mt-2">Quản lý ngưỡng cảnh báo (thresholds) cho hệ thống.</p>
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <GlassCard className="space-y-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="text-white font-semibold">Danh sách</div>
            <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" onClick={() => refresh()}>
              Refresh
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px]">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Code</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Enabled</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Severity</th>
                </tr>
              </thead>
              <tbody>
                {thresholds.map((t) => (
                  <tr
                    key={t.alert_code}
                    className={`border-b border-white/5 hover:bg-white/5 cursor-pointer ${selected === t.alert_code ? "bg-white/5" : ""}`}
                    onClick={() => setSelected(t.alert_code)}
                  >
                    <td className="py-2 px-3 text-white/90">{t.alert_code}</td>
                    <td className="py-2 px-3 text-white/70">{t.enabled ? "YES" : "NO"}</td>
                    <td className="py-2 px-3 text-white/70">{t.severity}</td>
                  </tr>
                ))}
                {thresholds.length === 0 ? (
                  <tr>
                    <td className="py-6 px-3 text-white/60" colSpan={3}>
                      Chưa có thresholds.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </GlassCard>

        <GlassCard className="space-y-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="text-white font-semibold">Chỉnh sửa</div>
            <div className="flex items-center gap-2">
              <button
                className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
                disabled={busy || !selected}
                onClick={() => reload()}
              >
                Reload cache
              </button>
            </div>
          </div>

          <div className="text-white/60 text-sm">Alert: <span className="text-white/90 font-semibold">{selected || "—"}</span></div>
          <div className="flex items-center gap-3 flex-wrap">
            <label className="text-white/70 text-sm flex items-center gap-2">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              Enabled
            </label>
            <div className="flex items-center gap-2">
              <span className="text-white/60 text-sm">Severity</span>
              <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="glass-input px-3 py-2 rounded-lg text-white text-sm">
                <option value="HIGH">HIGH</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="LOW">LOW</option>
              </select>
            </div>
          </div>

          <div className="space-y-1">
            <div className="text-white/60 text-sm">Params (JSON)</div>
            <textarea
              value={paramsJson}
              onChange={(e) => setParamsJson(e.target.value)}
              rows={10}
              className="glass-input w-full px-4 py-3 rounded-lg text-white text-xs font-mono"
            />
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              disabled={busy || !selected}
              onClick={() => save()}
            >
              Lưu
            </button>
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              disabled={busy || !selected}
              onClick={() => test()}
            >
              Test (latest metrics)
            </button>
          </div>

          {selectedRow?.updated_at && (
            <div className="text-white/40 text-xs">Updated: {selectedRow.updated_at}</div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}

