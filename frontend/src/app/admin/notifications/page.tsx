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

async function mutate<T>(url: string, method: "POST" | "DELETE"): Promise<T> {
  const response = await fetch(url, { method, headers: { "Content-Type": "application/json" } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

type NotificationChannel = {
  id: number;
  channel_type: string;
  enabled: boolean;
  config?: Record<string, any>;
  created_at?: string;
  updated_at?: string | null;
};

type NotificationEvent = {
  id?: number;
  alert_code?: string | null;
  channel_id?: number | null;
  channel_type?: string | null;
  status?: string | null;
  created_at?: string | null;
  error_message?: string | null;
  payload_json?: any;
};

export default function AdminNotificationsPage() {
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [events, setEvents] = useState<NotificationEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    setErr(null);
    const [c, e] = await Promise.all([
      fetchJson<NotificationChannel[]>("/api/admin/notifications"),
      fetchJson<NotificationEvent[]>("/api/admin/notifications/events?limit=50"),
    ]);
    setChannels(c);
    setEvents(e);
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e?.message || "Không thể tải notifications"));
  }, []);

  async function toggleChannel(id: number, enabled: boolean) {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await mutate<any>(`/api/admin/notifications/${id}/toggle?enabled=${enabled ? "true" : "false"}`, "POST");
      setMsg(`Đã ${res.enabled ? "bật" : "tắt"} channel ${id}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Toggle thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function deleteChannel(id: number) {
    try {
      if (!confirm(`Xóa channel ${id}?`)) return;
      setBusy(true);
      setMsg(null);
      setErr(null);
      await mutate<any>(`/api/admin/notifications/${id}`, "DELETE");
      setMsg(`Đã xóa channel ${id}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Delete thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Admin • Notifications</h1>
          <p className="text-white/60 mt-2">Kênh gửi cảnh báo (email/webhook) và lịch sử sự kiện gửi.</p>
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
            <div className="text-white font-semibold">Channels</div>
            <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" onClick={() => refresh()}>
              Refresh
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px]">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">ID</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Type</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Enabled</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Config</th>
                  <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Actions</th>
                </tr>
              </thead>
              <tbody>
                {channels.map((c) => (
                  <tr key={c.id} className="border-b border-white/5 hover:bg-white/5">
                    <td className="py-2 px-3 text-white/90">{c.id}</td>
                    <td className="py-2 px-3 text-white/70">{c.channel_type}</td>
                    <td className="py-2 px-3 text-white/70">{c.enabled ? "YES" : "NO"}</td>
                    <td className="py-2 px-3 text-white/50 text-xs whitespace-pre-wrap break-words">
                      {c.config ? JSON.stringify(c.config) : "—"}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          className="glass-button px-3 py-1.5 rounded-lg text-white text-xs hover:bg-white/10 disabled:opacity-50"
                          disabled={busy}
                          onClick={() => toggleChannel(c.id, !c.enabled)}
                        >
                          {c.enabled ? "Tắt" : "Bật"}
                        </button>
                        <button
                          className="glass-button px-3 py-1.5 rounded-lg text-white text-xs hover:bg-white/10 disabled:opacity-50"
                          disabled={busy}
                          onClick={() => deleteChannel(c.id)}
                        >
                          Xóa
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {channels.length === 0 ? (
                  <tr>
                    <td className="py-6 px-3 text-white/60" colSpan={5}>
                      Chưa có channel.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="text-white/40 text-xs">
            Ghi chú: form tạo channel (email/webhook) chưa đưa lên UI vì đang ưu tiên workflow local.
          </div>
        </GlassCard>

        <GlassCard className="space-y-3">
          <div className="text-white font-semibold">Events (gần đây)</div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[880px]">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Time</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Alert</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Channel</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Status</th>
                  <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Error</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e, idx) => (
                  <tr key={`${e.id || idx}`} className="border-b border-white/5 hover:bg-white/5">
                    <td className="py-2 px-3 text-white/60">{e.created_at || "—"}</td>
                    <td className="py-2 px-3 text-white/80">{e.alert_code || "—"}</td>
                    <td className="py-2 px-3 text-white/70">
                      {e.channel_type || "—"}#{e.channel_id ?? "—"}
                    </td>
                    <td className="py-2 px-3 text-white/80">{e.status || "—"}</td>
                    <td className="py-2 px-3 text-red-300 text-sm">{e.error_message || ""}</td>
                  </tr>
                ))}
                {events.length === 0 ? (
                  <tr>
                    <td className="py-6 px-3 text-white/60" colSpan={5}>
                      Chưa có event.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

