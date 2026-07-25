// The application pool: tiers -> companies -> their open roles.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const API_TOKEN = process.env.API_TOKEN || "";

export function apiHeaders(): Record<string, string> {
  return API_TOKEN
    ? { Authorization: `Bearer ${API_TOKEN}`, "Content-Type": "application/json" }
    : { "Content-Type": "application/json" };
}

export const API = API_BASE;

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: apiHeaders(),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export interface PoolRole {
  job_id: string;
  rank: number;
  title: string;
  location: string;
  in_canada: boolean;
  department: string | null;
  apply_url: string | null;
  posted_at: string | null;
  first_seen_at: string | null;
  deadline: string | null;
  freshness: number;
  priority: number | null;
  eligibility: string;
  role_band: string | null;
  role_type: string | null;
}

export interface PoolCompany {
  key: string;
  name: string;
  score: number;
  value: number;
  access: number;
  platform_tier: string;
  posture: string;
  safety_net: boolean;
  why: string;
  tags: string[];
  source_status: string;
  careers_url: string | null;
  total_roles: number;
  open_roles: number;
  canada_roles: number;
  top_roles: PoolRole[];
  has_more: boolean;
}

export interface PoolGroup {
  tier: string;
  company_count: number;
  open_roles: number;
  companies: PoolCompany[];
}

export interface Pool {
  groups: PoolGroup[];
  total_companies: number;
  total_open_roles: number;
  last_refreshed: string | null;
}

export interface CompanyPage extends Omit<PoolCompany, "top_roles" | "has_more"> {
  tier: string;
  platform_score: number;
  adjustment_reason: string | null;
  role_floor: boolean;
  worth_taking_if_offered: boolean;
  assessed_on: string;
  valid_until: string;
  inputs: Record<string, number>;
  source: {
    status: string;
    careers_url: string | null;
    connector: string | null;
    note: string | null;
    probed_on: string | null;
  };
  roles: PoolRole[];
  role_selection: {
    recommended_job_ids: string[];
    strong_job_ids: string[];
    backup_job_ids: string[];
    shortfall_message: string | null;
  };
  counts: { total: number; open: number; canada: number; eligible: number };
}

export interface RefreshStatus {
  running: boolean;
  total: number;
  done: number;
  percent: number;
  current: string;
  stage: string;
  eta_seconds: number;
  elapsed_seconds: number;
  finished_at: string | null;
  new_jobs: number;
  error: string | null;
  log: string[];
}

export const pool = {
  get: () => get<Pool>("/pool"),
  company: (key: string) => get<CompanyPage>(`/pool/company/${key}`),
  estimate: () =>
    get<{ sources: number; units: number; estimated_seconds: number }>(
      "/pool/refresh/estimate",
    ),
};

export const TIER_STYLE: Record<string, string> = {
  S: "border-emerald-600 text-emerald-300 bg-emerald-950/30",
  A: "border-blue-600 text-blue-300 bg-blue-950/30",
  B: "border-gray-500 text-gray-200 bg-gray-800/30",
  C: "border-gray-700 text-gray-400",
  D: "border-gray-800 text-gray-500",
};

export function eligibilityTone(g: string): string {
  if (g === "PASS") return "text-emerald-400";
  if (g === "REVIEW") return "text-amber-400";
  if (g === "FAIL") return "text-red-400";
  return "text-gray-500";
}
