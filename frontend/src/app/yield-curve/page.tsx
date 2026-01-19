import { YieldCurveClient } from "./YieldCurveClient";
import { YieldCurveRecord } from "@/lib/bondlabApi";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export default async function YieldCurvePage() {
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8001";
  let records: YieldCurveRecord[] = [];
  try {
    records = await fetchJson<YieldCurveRecord[]>(`${backendUrl}/api/yield-curve/latest`);
  } catch {
    records = [];
  }
  const initialDate = records[0]?.date || "";

  return <YieldCurveClient initialDate={initialDate} initialData={records} />;
}
