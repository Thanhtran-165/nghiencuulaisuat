import { SecondaryClient } from "./SecondaryClient";
import { SecondaryTradingRecord } from "@/lib/bondlabApi";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export default async function SecondaryPage() {
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8001";
  let rows: SecondaryTradingRecord[] = [];
  try {
    rows = await fetchJson<SecondaryTradingRecord[]>(`${backendUrl}/api/secondary/latest?limit=400`);
  } catch {
    rows = [];
  }
  const latestDate = rows[0]?.date || "";
  return <SecondaryClient initialRows={rows} initialEndDate={latestDate} />;
}
