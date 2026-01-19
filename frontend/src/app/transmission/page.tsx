import { TransmissionClient } from "./TransmissionClient";
import {
  TransmissionAlertRecord,
  TransmissionCoverageSummary,
  TransmissionMetricRecord,
  TransmissionProgressSummary,
  TransmissionScoreSummary,
} from "@/lib/bondlabApi";

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

export default async function TransmissionPage() {
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8001";

  const today = new Date();
  const rangeEnd = isoDate(today);
  const rangeStart = isoDate(new Date(today.getTime() - 180 * 24 * 60 * 60 * 1000));

  let latest: TransmissionMetricRecord[] = [];
  let scoreSeries: TransmissionMetricRecord[] = [];
  let alerts: TransmissionAlertRecord[] = [];
  let coverage: TransmissionCoverageSummary | null = null;
  let progress: TransmissionProgressSummary | null = null;
  let scoreSummary: TransmissionScoreSummary | null = null;

  try {
    [latest, scoreSeries, alerts, coverage, progress, scoreSummary] = await Promise.all([
      fetchJson<TransmissionMetricRecord[]>(`${backendUrl}/api/transmission/latest`),
      fetchJson<TransmissionMetricRecord[]>(`${backendUrl}/api/transmission/timeseries?metric_name=transmission_score&limit=90`),
      fetchJson<TransmissionAlertRecord[]>(`${backendUrl}/api/transmission/alerts?limit=30`),
      fetchJson<TransmissionCoverageSummary>(`${backendUrl}/api/transmission/coverage?start_date=${encodeURIComponent(rangeStart)}&end_date=${encodeURIComponent(rangeEnd)}`),
      fetchJson<TransmissionProgressSummary>(`${backendUrl}/api/transmission/progress?start_date=${encodeURIComponent(rangeStart)}&end_date=${encodeURIComponent(rangeEnd)}`),
      fetchJson<TransmissionScoreSummary>(`${backendUrl}/api/transmission/score-summary?start_date=${encodeURIComponent(rangeStart)}&end_date=${encodeURIComponent(rangeEnd)}`),
    ]);
  } catch {
    // Render gracefully with empty state; client can still refresh.
  }

  const initialDate = latest[0]?.date || rangeEnd;

  return (
    <TransmissionClient
      initialLatest={latest}
      initialScoreSeries={scoreSeries}
      initialAlerts={alerts}
      initialCoverage={coverage}
      initialProgress={progress}
      initialScoreSummary={scoreSummary}
      initialDate={initialDate}
      defaultRangeStart={rangeStart}
      defaultRangeEnd={rangeEnd}
    />
  );
}
