"use client";

import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import { bondlabApi, BondYStressRecord } from "@/lib/bondlabApi";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function fmtScore(v?: number | null) {
  if (v == null) return "—";
  return v.toFixed(1);
}

function fmtSignedScore(v?: number | null) {
  if (v == null) return "—";
  const s = v.toFixed(1);
  return v > 0 ? `+${s}` : s;
}

function fmtWeight(weight?: number | null) {
  if (weight == null) return "—";
  return `${(weight * 100).toFixed(0)}%`;
}

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

async function postJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: "POST", cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

type Driver = {
  name?: string;
  label?: string;
  metric?: string;
  weight?: number;
  contribution?: number;
  percentile?: number;
  value?: number;
};

function parseDrivers(record: BondYStressRecord | null): Driver[] {
  if (!record?.driver_json) return [];
  try {
    const parsed = JSON.parse(record.driver_json);
    if (!Array.isArray(parsed)) return [];
    return (parsed as any[]).map((d) => ({
      name: typeof d?.name === "string" ? d.name : undefined,
      label: typeof d?.label === "string" ? d.label : undefined,
      metric: typeof d?.metric === "string" ? d.metric : undefined,
      weight: typeof d?.weight === "number" ? d.weight : undefined,
      contribution: typeof d?.contribution === "number" ? d.contribution : undefined,
      percentile: typeof d?.percentile === "number" ? d.percentile : undefined,
      value: typeof d?.value === "number" ? d.value : undefined,
    }));
  } catch {
    return [];
  }
}

function bucketText(bucket?: string | null): { label: string; description: string } {
  switch (bucket) {
    case "S0":
      return { label: "Rất thấp", description: "Biến động thấp; thị trường tương đối ổn định." };
    case "S1":
      return { label: "Thấp", description: "Áp lực thấp; điều kiện nhìn chung ổn định." };
    case "S2":
      return { label: "Vừa", description: "Có dấu hiệu căng thẳng mức vừa; bức tranh chung đang đáng chú ý hơn bình thường." };
    case "S3":
      return { label: "Cao", description: "Căng thẳng cao; các chỉ báo đang lệch đáng kể so với bình thường." };
    case "S4":
      return { label: "Rất cao", description: "Căng thẳng rất cao; thị trường có thể biến động mạnh." };
    default:
      return { label: "—", description: "Chưa có dữ liệu để phân loại." };
  }
}

function driverPlainMeaning(contribution?: number | null) {
  if (contribution == null) return "Chưa đủ dữ liệu để giải thích.";
  if (contribution > 0) return "thường làm chỉ số Stress tăng";
  if (contribution < 0) return "thường làm chỉ số Stress giảm";
  return "đang ở mức trung tính";
}

function Glossary({
  items,
  title,
  defaultOpen = false,
}: {
  title: string;
  defaultOpen?: boolean;
  items: Array<{ term: string; def: string }>;
}) {
  return (
    <details className="glass-card rounded-2xl p-6" open={defaultOpen}>
      <summary className="cursor-pointer text-white font-semibold select-none">{title}</summary>
      <div className="mt-3 space-y-3">
        {items.map((it) => (
          <div key={it.term} className="text-sm">
            <div className="text-white/90 font-medium">{it.term}</div>
            <div className="text-white/60">{it.def}</div>
          </div>
        ))}
      </div>
    </details>
  );
}

function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        className="absolute inset-0 bg-black/60"
        aria-label="Close modal"
        onClick={onClose}
      />
      <div className="relative w-full max-w-3xl">
        <GlassCard className="p-0 overflow-hidden">
          <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between gap-3">
            <div className="text-white font-semibold">{title}</div>
            <button className="glass-button px-3 py-1.5 rounded-lg text-white/80 hover:text-white" onClick={onClose}>
              Đóng
            </button>
          </div>
          <div className="px-6 py-5">{children}</div>
        </GlassCard>
      </div>
    </div>
  );
}

export function StressClient({
  initialLatest,
  initialSeries,
  defaultStart,
  defaultEnd,
}: {
  initialLatest: BondYStressRecord | null;
  initialSeries: BondYStressRecord[];
  defaultStart: string;
  defaultEnd: string;
}) {
  const [latest, setLatest] = useState<BondYStressRecord | null>(initialLatest);
  const [series, setSeries] = useState<BondYStressRecord[]>(initialSeries);
  const [start, setStart] = useState(defaultStart);
  const [end, setEnd] = useState(defaultEnd);
  const [computeDate, setComputeDate] = useState<string>(initialLatest?.date || isoDate(new Date()));
  const [rangeBusy, setRangeBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [simpleView, setSimpleView] = useState(true);
  const [whyOpen, setWhyOpen] = useState(false);

  const drivers = useMemo(() => parseDrivers(latest).slice(0, 3), [latest]);
  const chartData = useMemo(() => {
    return [...series]
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((r) => ({
        date: r.date,
        stress: r.stress_index ?? null,
      }));
  }, [series]);

  const latestScore = latest?.stress_index ?? null;
  const latestBucket = latest?.regime_bucket ?? null;
  const bucket = useMemo(() => bucketText(latestBucket), [latestBucket]);

  const seriesSummary = useMemo(() => {
    const sorted = [...series].sort((a, b) => a.date.localeCompare(b.date));
    const n = sorted.length;
    const last = n ? (sorted[n - 1].stress_index ?? null) : null;
    const prev14 = n > 14 ? (sorted[n - 1 - 14].stress_index ?? null) : null;
    const prev30 = n > 30 ? (sorted[n - 1 - 30].stress_index ?? null) : null;
    const d14 = last != null && prev14 != null ? last - prev14 : null;
    const d30 = last != null && prev30 != null ? last - prev30 : null;
    return { n, d14, d30 };
  }, [series]);

  async function refresh() {
    setErr(null);
    const [l, s] = await Promise.all([
      bondlabApi.stressLatest(),
      bondlabApi.stressTimeseries({ start_date: start, end_date: end }),
    ]);
    setLatest(l[0] || null);
    setSeries(s);
  }

  async function computeOne() {
    if (!computeDate) return;
    try {
      setBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>(`/api/admin/stress/compute?target_date=${encodeURIComponent(computeDate)}`);
      setMsg(`Đã compute BondY Stress cho ${res?.date || computeDate}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Compute thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function computeRangeOnce() {
    try {
      setRangeBusy(true);
      setMsg(null);
      setErr(null);
      const res = await postJson<any>(
        `/api/admin/stress/compute-range?start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(
          end
        )}&max_dates=300&skip_existing=true`
      );
      const ok = Number(res?.succeeded ?? 0);
      const skipped = Number(res?.skipped ?? 0);
      const failed = Number(res?.failed ?? 0);
      const remaining = Number(res?.remaining ?? 0);
      setMsg(`Backfill stress: ok=${ok}, skip=${skipped}, fail=${failed}, còn lại=${remaining}`);
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Backfill thất bại");
    } finally {
      setRangeBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">Stress</h1>
          <p className="text-white/60 mt-2">
            “Nhiệt kế” căng thẳng thị trường (0–100). Số cao hơn = thị trường căng thẳng hơn.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            className={`glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 ${simpleView ? "active" : ""}`}
            onClick={() => setSimpleView(true)}
            title="Chỉ giữ phần dễ hiểu"
          >
            Xem đơn giản
          </button>
          <button
            className={`glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 ${!simpleView ? "active" : ""}`}
            onClick={() => setSimpleView(false)}
            title="Hiện thêm chi tiết kỹ thuật"
          >
            Xem chi tiết
          </button>
          <button className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" onClick={() => refresh()}>
            Refresh
          </button>
        </div>
      </div>

      {(msg || err) && (
        <GlassCard>
          {msg && <div className="text-emerald-200 text-sm">{msg}</div>}
          {err && <div className="text-red-300 text-sm">{err}</div>}
        </GlassCard>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Hôm nay</div>
          <div className="text-white text-2xl font-bold">{latest?.date || "—"}</div>
          <div className="text-white/60 text-sm">
            Mức: <span className="text-white/90 font-semibold">{bucket.label}</span>{" "}
            <span className="text-white/50">({latest?.regime_bucket || "—"})</span>
          </div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Stress index (0–100)</div>
          <div className="text-white text-3xl font-bold">{fmtScore(latestScore)}</div>
          <div className="text-white/60 text-sm">{bucket.description}</div>
          <div className="mt-2">
            <div className="h-2 rounded-full bg-white/10 overflow-hidden">
              <div
                className="h-2 rounded-full"
                style={{
                  width: `${Math.max(0, Math.min(100, Number(latestScore ?? 0)))}%`,
                  background: "linear-gradient(90deg, #00C897 0%, #FFD166 55%, #FF6B35 100%)",
                }}
                aria-label="Stress gauge"
              />
            </div>
            <div className="text-white/40 text-xs mt-1">0 = rất ổn định · 100 = rất căng thẳng</div>
          </div>
        </GlassCard>
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm flex items-center justify-between gap-3">
            <span>Vì sao?</span>
            <button className="glass-button px-3 py-1.5 rounded-lg text-white text-xs hover:bg-white/10" onClick={() => setWhyOpen(true)}>
              Xem giải thích
            </button>
          </div>
          {drivers.length ? (
            <div className="space-y-2">
              {drivers.map((d, idx) => (
                <div key={`${d.metric || d.label || "driver"}-${idx}`} className="text-sm">
                  <div className="text-white/90 font-medium truncate">{d.label || d.name || d.metric || "—"}</div>
                  <div className="text-white/60">
                    {driverPlainMeaning(d.contribution ?? null)}
                    {!simpleView && (
                      <span className="text-white/40">
                        {" "}
                        · đóng góp: {fmtSignedScore(d.contribution ?? null)} (điểm)
                        {d.value != null ? ` · mức chuẩn hoá: ${fmtScore(d.value)}/100` : ""}
                        {d.weight != null ? ` · trọng số: ${fmtWeight(d.weight)}` : ""}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-white/50 text-sm">Chưa đủ dữ liệu để tách “nguyên nhân”.</div>
          )}
          <div className="text-white/40 text-xs pt-2">
            Ghi chú: “Vì sao?” là mô tả thống kê (không khẳng định nhân quả, không phải khuyến nghị tài chính).
          </div>
        </GlassCard>
      </div>

      <Glossary
        title="Giải thích nhanh (dành cho người mới)"
        items={[
          {
            term: "Stress index (0–100)",
            def: "Một “nhiệt kế” tổng hợp: càng cao thì thị trường càng có dấu hiệu căng thẳng/biến động.",
          },
          {
            term: "Bucket (S0–S4)",
            def: "Nhóm mức độ căng thẳng. Ví dụ S3 là cao, S4 là rất cao. Đây là cách gắn nhãn để dễ đọc.",
          },
          {
            term: "Top drivers",
            def: "Các yếu tố đang làm chỉ số Stress lệch khỏi mức trung tính (50). Dương = đẩy Stress lên, âm = kéo Stress xuống.",
          },
          {
            term: "Chuẩn hoá (0–100)",
            def: "Để so sánh các yếu tố khác đơn vị (%, bps, khối lượng…), hệ thống đổi về cùng một thang đo 0–100.",
          },
          {
            term: "Trọng số",
            def: "Khi tổng hợp Stress, mỗi nhóm chỉ báo có mức quan trọng khác nhau. Trọng số càng cao thì driver đó tác động đến Stress mạnh hơn.",
          },
          {
            term: "Giới hạn",
            def: "Chỉ số dựa trên dữ liệu hiện có. Nếu thiếu dữ liệu/độ phủ ngắn, phần “Vì sao?” có thể kém ổn định hơn.",
          },
        ]}
      />

      <GlassCard>
        <div className="flex items-end justify-between gap-4 flex-wrap mb-4">
          <div>
            <div className="text-white font-semibold">Stress index (series)</div>
            <div className="text-white/50 text-sm">
              Khoảng thời gian bạn chọn · {seriesSummary.n} điểm dữ liệu
              {seriesSummary.d14 != null ? ` · Δ14 phiên: ${fmtSignedScore(seriesSummary.d14)} điểm` : ""}
              {seriesSummary.d30 != null ? ` · Δ30 phiên: ${fmtSignedScore(seriesSummary.d30)} điểm` : ""}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="glass-input px-4 py-2 rounded-lg text-white text-sm"
            />
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="glass-input px-4 py-2 rounded-lg text-white text-sm"
            />
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10"
              onClick={() => refresh()}
            >
              Tải lại
            </button>
          </div>
        </div>

        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis dataKey="date" stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} />
            <YAxis stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} domain={[0, 100]} />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(15, 23, 42, 0.9)",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "12px",
              }}
              labelStyle={{ color: "rgba(255,255,255,0.8)" }}
              formatter={(value: any) => (value == null ? "—" : Number(value).toFixed(1))}
            />
            <Line type="monotone" dataKey="stress" stroke="#FF6B35" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </GlassCard>

      {!simpleView && (
        <GlassCard className="space-y-3">
          <div className="text-white font-semibold">Công cụ (admin)</div>
          <div className="text-white/50 text-sm">
            Dùng khi cần rebuild stress. Stress phụ thuộc Transmission score nên nếu Transmission đang thiếu dữ liệu, stress có thể không tính được.
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="date"
              value={computeDate}
              onChange={(e) => setComputeDate(e.target.value)}
              className="glass-input px-4 py-2 rounded-lg text-white text-sm"
            />
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              disabled={busy || !computeDate}
              onClick={() => computeOne()}
            >
              Compute 1 ngày
            </button>
            <button
              className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10 disabled:opacity-50"
              disabled={rangeBusy}
              onClick={() => computeRangeOnce()}
              title="Tính theo range ở phía trên (start/end) — chạy theo batch 300 ngày mỗi lần"
            >
              Backfill theo range (batch)
            </button>
          </div>
        </GlassCard>
      )}

      <Modal open={whyOpen} title="Vì sao Stress tăng/giảm? (giải thích dễ hiểu)" onClose={() => setWhyOpen(false)}>
        <div className="space-y-4">
          <div className="text-white/70 text-sm">
            Mục tiêu của phần này là chuyển “số” → “thông tin”. Các câu dưới đây là mô tả thống kê dựa trên dữ liệu, không khẳng định nhân quả
            và không phải khuyến nghị tài chính.
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="glass-card rounded-xl p-4">
              <div className="text-white/60 text-xs">Cách đọc nhanh</div>
              <div className="text-white/90 text-sm mt-1">
                Stress hôm nay: <span className="font-semibold">{fmtScore(latestScore)}</span> ({latestBucket || "—"} — {bucket.label})
              </div>
              <div className="text-white/60 text-sm mt-2">
                Nếu một driver có “đóng góp” dương, nó thường kéo Stress tăng; đóng góp âm thì thường kéo Stress giảm.
              </div>
            </div>

            <div className="glass-card rounded-xl p-4">
              <div className="text-white/60 text-xs">Độ phủ dữ liệu</div>
              <div className="text-white/90 text-sm mt-1">{seriesSummary.n} điểm trong khoảng bạn chọn</div>
              <div className="text-white/60 text-sm mt-2">
                Nếu khoảng dữ liệu ngắn hoặc nhiều ngày thiếu, diễn giải có thể kém ổn định.
              </div>
            </div>
          </div>

          <div className="glass-card rounded-xl p-4">
            <div className="text-white/90 font-semibold text-sm">Bằng chứng chính (Top drivers)</div>
            <div className="mt-3 space-y-3">
              {drivers.length ? (
                drivers.map((d, idx) => (
                  <div key={`${d.metric || d.label || "driver-modal"}-${idx}`} className="text-sm">
                    <div className="text-white/90 font-medium">
                      {d.label || d.name || d.metric || "—"}{" "}
                      <span className="text-white/50 font-normal">({driverPlainMeaning(d.contribution ?? null)})</span>
                    </div>
                    <div className="text-white/60 mt-1">
                      {d.value != null ? `Mức chuẩn hoá: ${fmtScore(d.value)}/100.` : "Mức chuẩn hoá: —."}{" "}
                      {d.contribution != null ? `Đóng góp: ${fmtSignedScore(d.contribution)} điểm.` : "Đóng góp: —."}
                      {d.weight != null ? ` Trọng số: ${fmtWeight(d.weight)}.` : ""}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-white/60">Chưa đủ dữ liệu để tách driver.</div>
              )}
            </div>
          </div>

          <div className="text-white/50 text-xs">
            Gợi ý đọc: khi Stress tăng đột ngột, hãy nhìn driver nào “đóng góp” lớn nhất (theo trị tuyệt đối) để biết yếu tố nào đang lệch mạnh.
          </div>
        </div>
      </Modal>
    </div>
  );
}
