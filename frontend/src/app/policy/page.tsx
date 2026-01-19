import { PolicyClient } from "./PolicyClient";
import { PolicyRateRecord } from "@/lib/bondlabApi";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any)?.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export default async function PolicyPage() {
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8001";
  let latest: PolicyRateRecord[] = [];
  try {
    latest = await fetchJson<PolicyRateRecord[]>(`${backendUrl}/api/policy-rates/latest`);
  } catch {
    latest = [];
  }
  return <PolicyClient initialLatest={latest} />;
}
