import { AuctionsClient } from "./AuctionsClient";
import { AuctionRecord } from "@/lib/bondlabApi";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export default async function AuctionsPage() {
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8001";
  let rows: AuctionRecord[] = [];
  try {
    rows = await fetchJson<AuctionRecord[]>(`${backendUrl}/api/auctions/latest?limit=200`);
  } catch {
    rows = [];
  }
  const latestDate = rows[0]?.date || "";
  return <AuctionsClient initialRows={rows} initialEndDate={latestDate} />;
}
