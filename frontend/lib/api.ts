export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api/backend";

export type Metrics = {
  store_id: string;
  run_id: string | null;
  footfall: number;
  customer_sessions: number;
  staff_tracks: number;
  pos_invoices: number;
  matched_purchases: number;
  conversion_rate: number;
  avg_dwell_seconds: number;
  active_visitors: number;
  anomaly_count: number;
};

export type FunnelResponse = {
  run_id: string | null;
  steps: { name: string; count: number }[];
};

export type HeatmapResponse = {
  zones: { zone_id: string; name: string; zone_type: string; visits: number; avg_dwell_seconds: number }[];
};

export type EventItem = {
  id: string;
  event_type: string;
  camera_id: string | null;
  session_id: string | null;
  zone_id: string | null;
  occurred_at: string;
  payload: Record<string, unknown>;
};

export type AnomalyItem = {
  id: string;
  type: string;
  severity: string;
  occurred_at: string;
  entity_id: string | null;
  description: string;
};

export type SessionItem = {
  id: string;
  started_at: string;
  ended_at: string | null;
  dwell_seconds: number | null;
  matched_invoice: string | null;
  is_staff: boolean;
  reentry_count: number;
};

export type RunStatus = {
  run_id: string;
  status: string;
  processed_frames: number;
  events: number;
  started_at: string;
  finished_at: string | null;
  error: string | null;
  config: Record<string, unknown>;
};

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function withRunId(path: string, runId?: string | null) {
  if (!runId) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}run_id=${encodeURIComponent(runId)}`;
}

export async function fetchRunStatus(runId: string) {
  return fetchJson<RunStatus>(`/ingest/runs/${runId}`);
}

export async function fetchDashboard(runId?: string | null) {
  const [metrics, funnel, heatmap, events, anomalies, sessions] = await Promise.all([
    fetchJson<Metrics>(withRunId("/Metrics", runId)),
    fetchJson<FunnelResponse>(withRunId("/funnel", runId)),
    fetchJson<HeatmapResponse>(withRunId("/zones/heatmap", runId)),
    fetchJson<{ events: EventItem[] }>(withRunId("/events?limit=30", runId)),
    fetchJson<{ anomalies: AnomalyItem[] }>(withRunId("/anomalies", runId)),
    fetchJson<{ sessions: SessionItem[] }>(withRunId("/sessions?limit=30", runId))
  ]);

  return { metrics, funnel, heatmap, events: events.events, anomalies: anomalies.anomalies, sessions: sessions.sessions };
}
