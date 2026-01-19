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

type DatasetCatalogResponse = {
  catalog_date: string;
  datasets: DatasetCatalogItem[];
};

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export default async function DataPage() {
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8001";
  let payload: DatasetCatalogResponse | null = null;
  let error: string | null = null;

  try {
    payload = await fetchJson<DatasetCatalogResponse>(`${backendUrl}/api/data/catalog`);
  } catch (e: any) {
    error = e?.message || "Không thể tải catalog";
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">Data</h1>
        <p className="text-white/60 mt-2">
          Danh mục dữ liệu đang có trong DB (kèm thống kê cơ bản). Đây là tab theo dõi, không phải phân tích.
        </p>
      </div>

      {error && (
        <GlassCard>
          <div className="text-red-300 text-sm">{error}</div>
        </GlassCard>
      )}

      <GlassCard className="space-y-3">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="text-white font-semibold">Dataset catalog</div>
            <div className="text-white/50 text-sm">Ngày cập nhật: {payload?.catalog_date || "—"}</div>
          </div>
          <div className="text-white/50 text-sm">
            Tổng: <span className="text-white/80 font-semibold">{payload?.datasets?.length ?? "—"}</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px]">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Dataset</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Provider</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Bảng</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-white/60">Rows</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Min</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Max</th>
                <th className="text-left py-2 px-3 text-sm font-medium text-white/60">Historical</th>
              </tr>
            </thead>
            <tbody>
              {(payload?.datasets || []).map((d) => (
                <tr key={d.id} className="border-b border-white/5 hover:bg-white/5">
                  <td className="py-2 px-3 text-white/90">
                    <Link className="underline hover:text-white" href={`/data/${encodeURIComponent(d.id)}`}>
                      {d.name}
                    </Link>
                    <div className="text-white/40 text-xs">{d.id}</div>
                  </td>
                  <td className="py-2 px-3 text-white/70">{d.provider}</td>
                  <td className="py-2 px-3 text-white/70">{d.table}</td>
                  <td className="py-2 px-3 text-right text-white/90">
                    {d.stats?.rows == null ? "—" : d.stats.rows.toLocaleString()}
                  </td>
                  <td className="py-2 px-3 text-white/60">{d.stats?.min_date || "—"}</td>
                  <td className="py-2 px-3 text-white/60">{d.stats?.max_date || "—"}</td>
                  <td className="py-2 px-3 text-white/60">
                    {d.supports_historical ? (
                      <span className="text-emerald-200">YES</span>
                    ) : (
                      <span className="text-amber-200">Daily accumulate</span>
                    )}
                  </td>
                </tr>
              ))}

              {!payload?.datasets?.length ? (
                <tr>
                  <td className="py-6 px-3 text-white/60" colSpan={7}>
                    Chưa có dữ liệu catalog hoặc backend chưa sẵn sàng.
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
