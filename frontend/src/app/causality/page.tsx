import { CausalityClient } from "./CausalityClient";
import { CausalitySeriesCoverage, CausalitySeriesInfo } from "@/lib/bondlabApi";

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export default async function CausalityPage() {
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8001";
  const today = new Date();
  const end = isoDate(today);
  const start = isoDate(new Date(today.getTime() - 180 * 24 * 60 * 60 * 1000));

  let series: CausalitySeriesInfo[] = [];
  let coverage: CausalitySeriesCoverage[] = [];
  try {
    [series, coverage] = await Promise.all([
      fetchJson<CausalitySeriesInfo[]>(`${backendUrl}/api/transmission/causality/series`),
      fetchJson<CausalitySeriesCoverage[]>(
        `${backendUrl}/api/transmission/causality/availability?start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}`
      ),
    ]);
  } catch {
    // ok
  }

  return <CausalityClient initialSeries={series} initialCoverage={coverage} defaultStart={start} defaultEnd={end} />;
}
