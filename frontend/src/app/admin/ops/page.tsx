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

type BackupInfo = {
  path?: string;
  backup_path?: string;
  created_at?: string;
  size_bytes?: number;
};

export default function AdminOpsPage() {
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<any>(null);

  async function refresh() {
    setErr(null);
    const b = await fetchJson<any[]>("/api/admin/ops/backups");
    setBackups(b);
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e?.message || "Không thể tải backups"));
  }, []);

  async function createBackup() {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>("/api/admin/ops/backup");
      setMsg(`Đã tạo backup: ${res.backup_path || res.path || "—"}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Backup thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function verify(backupPath: string) {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>(`/api/admin/ops/verify-backup?backup_path=${encodeURIComponent(backupPath)}`);
      setVerifyResult(res);
      setMsg(`Verify: ${backupPath}`);
    } catch (e: any) {
      setErr(e?.message || "Verify thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function restore(backupPath: string) {
    try {
      if (!confirm(`RESTORE DB từ backup?\n${backupPath}\n\nCảnh báo: thao tác này ghi đè DB hiện tại.`)) return;
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>(
        `/api/admin/ops/restore?backup_path=${encodeURIComponent(backupPath)}&confirm=true`
      );
      setMsg(res?.message || "Restored");
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Restore thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Admin • Ops</h1>
          <p className="text-white/60 mt-2">Backup/restore DB (local). Restore có thể bị khóa bởi backend (ALLOW_RESTORE).</p>
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
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="text-white font-semibold">Backups</div>
          <div className="flex items-center gap-2">
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              disabled={busy}
              onClick={() => createBackup()}
            >
              Tạo backup
            </button>
            <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" onClick={() => refresh()}>
              Refresh
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px]">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Path</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Created</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Size</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Actions</th>
              </tr>
            </thead>
            <tbody>
              {backups.map((b, idx) => {
                const path = b.path || b.backup_path || "";
                return (
                  <tr key={`${path || idx}`} className="border-b border-white/5 hover:bg-white/5">
                    <td className="py-2 px-3 text-white/80 break-words">{path || "—"}</td>
                    <td className="py-2 px-3 text-white/60">{b.created_at || "—"}</td>
                    <td className="py-2 px-3 text-right text-white/60">
                      {b.size_bytes == null ? "—" : (b.size_bytes / 1024 / 1024).toFixed(2) + " MB"}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          className="glass-button px-3 py-1.5 rounded-lg text-white text-xs hover:bg-white/10 disabled:opacity-50"
                          disabled={busy || !path}
                          onClick={() => verify(path)}
                        >
                          Verify
                        </button>
                        <button
                          className="glass-button px-3 py-1.5 rounded-lg text-white text-xs hover:bg-white/10 disabled:opacity-50"
                          disabled={busy || !path}
                          onClick={() => restore(path)}
                        >
                          Restore
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {backups.length === 0 ? (
                <tr>
                  <td className="py-6 px-3 text-white/60" colSpan={4}>
                    Chưa có backup.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {verifyResult && (
        <GlassCard className="space-y-3">
          <div className="text-white font-semibold">Verify result</div>
          <pre className="text-white/70 text-xs whitespace-pre-wrap break-words">{JSON.stringify(verifyResult, null, 2)}</pre>
        </GlassCard>
      )}
    </div>
  );
}

