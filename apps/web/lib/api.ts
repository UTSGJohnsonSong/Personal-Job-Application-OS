const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export interface Overview {
  totals: Record<string, number>;
  by_status: Record<string, number>;
  conversion: Record<string, number>;
  funnel: { stage: string; count: number }[];
}

export interface ActionItems {
  packets_waiting_confirmation: number;
  deadlines_within_48h: number;
  stale_submitted_over_2w: number;
}

export interface JobItem {
  id: string;
  title: string;
  remote_mode: string | null;
  canonical_application_url: string | null;
  current_status: string;
  inbox_category: string;
  freshness_score: number;
  source_priority: number;
}

export const api = {
  overview: () => get<Overview>("/dashboard/overview"),
  actionItems: () => get<ActionItems>("/dashboard/action-items"),
  jobs: (category?: string) =>
    get<{ items: JobItem[]; count: number }>(
      `/jobs${category ? `?category=${encodeURIComponent(category)}` : ""}`,
    ),
  prepareConfirmation: (appId: string) =>
    post<{ packet_hash: string; message: string }>(
      `/applications/${appId}/prepare-confirmation`,
      {},
    ),
  confirmAndSubmit: (appId: string, packetHashAck: string) =>
    post<{ status: string }>(`/applications/${appId}/confirm-and-submit`, {
      packet_hash_ack: packetHashAck,
    }),
};
