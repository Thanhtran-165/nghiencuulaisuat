"use client";

import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import { bondlabApi, InsightsHorizon, InsightsPayload } from "@/lib/bondlabApi";

function formatScore(score?: number) {
  if (score == null) return "—";
  return score.toFixed(1);
}

function statusLabel(status: InsightsHorizon["status"]) {
  if (status === "ready") return "Đủ dữ liệu";
  if (status === "fallback") return "Tạm thời (fallback)";
  if (status === "limited") return "Chờ dữ liệu";
  return "Thiếu dữ liệu";
}

function statusTone(status: InsightsHorizon["status"]) {
  if (status === "ready")
    return "inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-200 border border-emerald-500/20";
  if (status === "fallback")
    return "inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold bg-yellow-500/15 text-yellow-200 border border-yellow-500/20";
  if (status === "limited")
    return "inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold bg-white/10 text-white/70 border border-white/10";
  return "inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold bg-red-500/15 text-red-200 border border-red-500/20";
}

function horizonTitle(h: InsightsHorizon) {
  if (h.title) return h.title;
  if (h.horizon_type === "short") return "Ngắn hạn";
  if (h.horizon_type === "mid") return "Trung hạn";
  return "Dài hạn";
}

export default function NhanDinhPage() {
  const [data, setData] = useState<InsightsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    bondlabApi
      .insightsHorizons()
      .then((payload) => {
        if (!alive) return;
        setData(payload);
      })
      .catch((e) => {
        if (!alive) return;
        setError(e?.message || "Không thể tải dữ liệu");
      })
      .finally(() => {
        if (!alive) return;
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const horizons = useMemo(() => {
    const short = data?.horizons?.short;
    const mid = data?.horizons?.mid;
    const long = data?.horizons?.long;
    return [short, mid, long].filter(Boolean) as InsightsHorizon[];
  }, [data]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">Nhận định</h1>
        <p className="text-white/60 mt-2">
          Tóm tắt điều kiện thị trường theo 3 thời hạn (tính theo “phiên”, không phải calendar days).
        </p>
      </div>

      <GlassCard>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="text-white font-semibold">VM-CI (tổng quan)</div>
            <div className="text-white/60 text-sm mt-1">
              Score:{" "}
              <span className="text-white">{formatScore(data?.vmci_overall?.score)}</span>
              {" • "}
              Bucket:{" "}
              <span className="text-white">{data?.vmci_overall?.bucket || "—"}</span>
            </div>
          </div>
          {data?.vmci_overall?.note && (
            <div className="text-white/40 text-sm max-w-xl">
              {data.vmci_overall.note}
            </div>
          )}
        </div>
      </GlassCard>

      {loading && (
        <GlassCard>
          <div className="text-white/60">Đang tải…</div>
        </GlassCard>
      )}

      {error && (
        <GlassCard>
          <div className="text-red-300 font-semibold mb-1">Lỗi</div>
          <div className="text-white/60 text-sm">{error}</div>
          <div className="text-white/40 text-sm mt-2">
            Gợi ý: chạy backend trên `http://127.0.0.1:8001`.
          </div>
        </GlassCard>
      )}

      {!loading && !error && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {horizons.map((h) => (
            <GlassCard key={h.horizon_type} className="space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-white font-semibold">{horizonTitle(h)}</div>
                  {h.subtitle && (
                    <div className="text-white/50 text-sm mt-1">{h.subtitle}</div>
                  )}
                </div>
                <span className={statusTone(h.status)}>{statusLabel(h.status)}</span>
              </div>

              <div className="text-white/80">{h.conclusion || "Chưa đủ dữ liệu để đánh giá."}</div>

              <div className="text-white/50 text-sm">
                {h.readiness_info?.primary_series && (
                  <div>
                    Nguồn chính: <span className="text-white/70">{h.readiness_info.primary_series}</span>
                  </div>
                )}
                {h.readiness_info?.required_pairs != null && (
                  <div>
                    Cặp hợp lệ:{" "}
                    <span className="text-white/70">
                      {h.readiness_info.valid_pairs ?? 0}/{h.readiness_info.required_pairs}
                    </span>
                    {h.readiness_info.horizon_used != null && (
                      <>
                        {" • "}
                        Δ<span className="text-white/70">{h.readiness_info.horizon_used}</span> phiên
                      </>
                    )}
                  </div>
                )}
              </div>

              <details className="mt-2">
                <summary className="cursor-pointer text-white/70 hover:text-white text-sm">
                  Vì sao? (bằng chứng & limitations)
                </summary>
                <div className="mt-3 space-y-2 text-sm">
                  {h.evidence?.stress_overlay?.label && (
                    <div className="glass-card rounded-xl p-3">
                      <div className="text-yellow-200 font-semibold">{h.evidence.stress_overlay.label}</div>
                      {h.evidence.stress_overlay.explanation && (
                        <div className="text-white/60 mt-1">{h.evidence.stress_overlay.explanation}</div>
                      )}
                    </div>
                  )}

                  {h.evidence?.term_premium_proxy?.label && (
                    <div className="glass-card rounded-xl p-3">
                      <div className="text-white/80 font-semibold">Proxy chênh lệch dài–ngắn</div>
                      <div className="text-white/60 mt-1">{h.evidence.term_premium_proxy.label}</div>
                      {h.evidence.term_premium_proxy.note && (
                        <div className="text-white/50 mt-1">{h.evidence.term_premium_proxy.note}</div>
                      )}
                    </div>
                  )}

                  {h.evidence?.limitations?.length ? (
                    <div className="glass-card rounded-xl p-3">
                      <div className="text-white/80 font-semibold">Limitations</div>
                      <ul className="list-disc pl-5 mt-1 text-white/60 space-y-1">
                        {h.evidence.limitations.map((x, idx) => (
                          <li key={idx}>{x}</li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <div className="text-white/50">Chưa có limitations.</div>
                  )}
                </div>
              </details>
            </GlassCard>
          ))}
        </div>
      )}

      <GlassCard>
        <div className="text-white/70 text-sm">
          Đây là thông tin về điều kiện thị trường, không phải khuyến nghị tài chính.
        </div>
      </GlassCard>
    </div>
  );
}
