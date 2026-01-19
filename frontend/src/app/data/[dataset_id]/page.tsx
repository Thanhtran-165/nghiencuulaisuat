import Link from "next/link";
import { GlassCard } from "@/components/GlassCard";

type DatasetStats = {
  rows: number;
  min_date?: string | null;
  max_date?: string | null;
};

type DatasetCatalogItem = {
  id: string;
  name: string;
  description: string;
  provider: string;
  url: string;
  access_method: string;
  supports_historical: boolean;
  earliest_known_date?: string | null;
  accumulation_start?: string | null;
  provenance: string;
  table: string;
  frequency: string;
  stats?: DatasetStats | null;
};

type DatasetDetailResponse = {
  dataset: DatasetCatalogItem;
  columns: Array<{ name: string; type: string; not_null: boolean; default: any; pk: boolean }>;
  sample: Array<Record<string, any>>;
};

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export default async function DatasetDetailPage({ params }: { params: Promise<{ dataset_id: string }> }) {
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8001";
  const { dataset_id } = await params;
  const datasetId = decodeURIComponent(dataset_id);

  let payload: DatasetDetailResponse | null = null;
  let error: string | null = null;

  try {
    payload = await fetchJson<DatasetDetailResponse>(`${backendUrl}/api/data/${encodeURIComponent(datasetId)}?limit=50`);
  } catch (e: any) {
    error = e?.message || "Không thể tải dataset";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-white">{payload?.dataset?.name || datasetId}</h1>
          <p className="text-white/60 mt-2">{payload?.dataset?.description || "—"}</p>
        </div>
        <Link className="glass-button px-4 py-2 rounded-lg text-white text-sm hover:bg-white/10" href="/data">
          ← Quay lại Data
        </Link>
      </div>

      {error && (
        <GlassCard>
          <div className="text-red-300 text-sm">{error}</div>
        </GlassCard>
      )}

      {payload?.dataset && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <GlassCard className="space-y-2">
            <div className="text-white/60 text-sm">Provider</div>
            <div className="text-white font-semibold">{payload.dataset.provider}</div>
            <div className="text-white/40 text-xs">{payload.dataset.provenance}</div>
          </GlassCard>
          <GlassCard className="space-y-2">
            <div className="text-white/60 text-sm">Table</div>
            <div className="text-white font-semibold">{payload.dataset.table}</div>
            <div className="text-white/40 text-xs">{payload.dataset.frequency}</div>
          </GlassCard>
          <GlassCard className="space-y-2">
            <div className="text-white/60 text-sm">Rows / Range</div>
            <div className="text-white font-semibold">
              {payload.dataset.stats?.rows == null ? "—" : payload.dataset.stats.rows.toLocaleString()}
            </div>
            <div className="text-white/40 text-xs">
              {payload.dataset.stats?.min_date || "—"} → {payload.dataset.stats?.max_date || "—"}
            </div>
          </GlassCard>
        </div>
      )}

      {payload?.dataset?.url && (
        <GlassCard className="space-y-2">
          <div className="text-white/60 text-sm">Nguồn</div>
          <div className="text-white/80 text-sm break-words">{payload.dataset.url}</div>
          <div className="text-white/40 text-xs">{payload.dataset.access_method}</div>
        </GlassCard>
      )}

      <GlassCard className="space-y-3">
        <div className="text-white font-semibold">Schema</div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px]">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Column</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Type</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Not null</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">PK</th>
              </tr>
            </thead>
            <tbody>
              {(payload?.columns || []).map((c) => (
                <tr key={c.name} className="border-b border-white/5 hover:bg-white/5">
                  <td className="py-2 px-3 text-white/90">{c.name}</td>
                  <td className="py-2 px-3 text-white/70">{c.type}</td>
                  <td className="py-2 px-3 text-white/70">{c.not_null ? "YES" : "NO"}</td>
                  <td className="py-2 px-3 text-white/70">{c.pk ? "YES" : "NO"}</td>
                </tr>
              ))}
              {!payload?.columns?.length ? (
                <tr>
                  <td className="py-6 px-3 text-white/60" colSpan={4}>
                    Không có schema hoặc DB chưa sẵn sàng.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </GlassCard>

      <GlassCard className="space-y-3">
        <div className="text-white font-semibold">Sample (limit 50)</div>
        <div className="text-white/50 text-sm">
          Mẫu đọc-only để hiểu dữ liệu. Nếu sample rỗng: dataset chưa có dữ liệu hoặc backend không truy vấn được.
        </div>
        <pre className="text-white/70 text-xs whitespace-pre-wrap break-words">
          {JSON.stringify(payload?.sample || [], null, 2)}
        </pre>
      </GlassCard>
    </div>
  );
}
