"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Props = {
  className?: string;
};

export function ManualIngestButton(props: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await fetch("/api/admin/ingest/daily", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as any)?.detail || `HTTP ${res.status}`);
      }
      const body = (await res.json().catch(() => ({}))) as any;
      const providers = Array.isArray(body?.providers) ? body.providers.join(", ") : "";
      setMsg(`Đã chạy ingest daily${providers ? ` (${providers})` : ""}.`);
      router.refresh();
    } catch (e: any) {
      setErr(e?.message || "Chạy ingest thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={props.className}>
      <div className="flex items-center gap-3 flex-wrap">
        <button
          className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
          disabled={busy}
          onClick={() => run()}
          title="Chạy ingest daily để kiểm tra dữ liệu mới (có thể mất 1–2 phút)"
        >
          {busy ? "Đang cập nhật dữ liệu..." : "Cập nhật dữ liệu"}
        </button>
        <div className="text-white/40 text-xs">
          Dùng khi bạn muốn kiểm tra ngay, thay vì chờ lịch 18:05.
        </div>
      </div>
      {msg ? <div className="text-emerald-200 text-xs mt-2">{msg}</div> : null}
      {err ? <div className="text-red-300 text-xs mt-2">{err}</div> : null}
    </div>
  );
}

