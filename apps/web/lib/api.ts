// Server-side API client. The token lives ONLY on the server (no NEXT_PUBLIC_
// prefix), so it is never shipped to the browser.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const API_TOKEN = process.env.API_TOKEN || "";

function authHeaders(): Record<string, string> {
  return API_TOKEN
    ? { Authorization: `Bearer ${API_TOKEN}`, "Content-Type": "application/json" }
    : { "Content-Type": "application/json" };
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: authHeaders(),
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
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

export interface QueueItem {
  application_id: string;
  job_id: string;
  title: string;
  status: string;
  queue_note: string | null;
  queue_priority: number | null;
  apply_url: string | null;
  deadline: string | null;
  freshness: number | null;
  source_status: string;
  score: number | null;
  strategy: string | null;
  suggested_minutes: number | null;
  why: string[];
  why_not: string[];
  eligibility: string | null;
  needs_confirmation: boolean;
  unknowns: string[];
}

export interface RecordAnswer {
  question: string;
  answer: string | null;
  field_type: string | null;
  is_sensitive: boolean;
  needs_user_input: boolean;
  answer_source: string | null;
  provenance: string;
  user_confirmed: boolean;
}

export interface ApplicationRecord {
  application_id: string;
  status: string;
  submitted_at: string | null;
  job: { id: string | null; title: string | null; apply_url: string | null };
  resume_version: { id: string; name: string; direction: string | null } | null;
  cover_letter: string | null;
  answers: RecordAnswer[];
  risks: string[];
  uncertainties: string[];
  timeline: { at: string; event: string; from: string | null; to: string | null }[];
}

export interface AmmoBlock {
  id: string;
  category: string;
  title: string;
  content: string;
  tags: string[];
  direction: string | null;
  is_master: boolean;
  contains_metrics: boolean;
  usage_count: number;
  provenance: string;
  user_confirmed: boolean;
  variants?: AmmoBlock[];
}

export const api = {
  overview: () => get<Overview>("/dashboard/overview"),
  actionItems: () => get<ActionItems>("/dashboard/action-items"),
  jobs: (category?: string) =>
    get<{ items: JobItem[]; count: number }>(
      `/jobs${category ? `?category=${encodeURIComponent(category)}` : ""}`,
    ),
  queue: () => get<{ count: number; items: QueueItem[]; warnings: unknown[] }>("/queue"),
  addToQueue: (jobId: string, note?: string) =>
    send<{ application_id: string }>("POST", `/queue/${jobId}`, { note }),
  removeFromQueue: (jobId: string) => send<unknown>("DELETE", `/queue/${jobId}`),
  records: (status?: string) =>
    get<{ count: number; items: { application_id: string; title: string; status: string;
      submitted_at: string | null; apply_url: string | null }[] }>(
      `/records${status ? `?status=${status}` : ""}`,
    ),
  record: (id: string) => get<ApplicationRecord>(`/records/${id}`),
  setStatus: (id: string, status: string, note?: string) =>
    send<unknown>("POST", `/records/${id}/status`, { status, note }),
  ammo: (params?: { category?: string; direction?: string; q?: string }) => {
    const qs = new URLSearchParams(
      Object.entries(params ?? {}).filter(([, v]) => v) as [string, string][],
    ).toString();
    return get<{ count: number; groups: AmmoBlock[] }>(`/ammo${qs ? `?${qs}` : ""}`);
  },
};
