import { InterbankClient } from "./InterbankClient";
import { InterbankCompareResponse } from "@/lib/bondlabApi";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export default async function InterbankPage() {
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8001";
  let compare: InterbankCompareResponse = { rows: [] };
  try {
    compare = await fetchJson<InterbankCompareResponse>(`${backendUrl}/api/interbank/compare`);
  } catch {
    compare = { rows: [] };
  }

  return <InterbankClient initialCompare={compare} />;
}
