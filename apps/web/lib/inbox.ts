// Company-tier-centric inbox client.
// Tier organises companies; Application Priority orders roles.
// `application_priority` is 0-100 — never a match percentage.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const API_TOKEN = process.env.API_TOKEN || "";

function headers(): Record<string, string> {
  return API_TOKEN
    ? { Authorization: `Bearer ${API_TOKEN}`, "Content-Type": "application/json" }
    : { "Content-Type": "application/json" };
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", headers: headers() });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST", headers: headers(), body: JSON.stringify(body), cache: "no-store",
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export interface TopRole {
  job_id: string;
  title: string;
  application_priority: number;
  role_band: string;
  role_type: string;
  eligibility: string;
  current_fit: number;
  role_strategic_value: number;
  evidence_coverage: number;
  is_official: boolean;
  apply_url: string | null;
}

export interface CompanyCard {
  company_id: string;
  name: string;
  tier: string;
  tier_display: string;
  provisional: boolean;
  platform_value: number;
  evidence_coverage: number;
  official_source_coverage: number;
  last_synced_at: string | null;
  high_potential_unrated: boolean;
  total_open_roles: number;
  canada_roles: number;
  gta_roles: number;
  student_roles: number;
  relevant_roles: number;
  submitted_applications: number;
  recommended_count: number;
  top_roles: TopRole[];
}

export interface TierGroup {
  tier: string;
  company_count: number;
  role_count: number;
  companies: CompanyCard[];
}

export interface GlobalRow {
  global_rank: number;
  company_id: string;
  company: string;
  company_tier: string;
  company_platform_value: number;
  job_id: string;
  title: string;
  role_band: string;
  role_type: string;
  eligibility: string;
  application_priority: number;
  role_strategic_value: number;
  current_fit: number;
  evidence_coverage: number;
  recommendation: string;
  is_official: boolean;
  apply_url: string | null;
}

export interface DetailRole extends TopRole {
  role_family: string;
  team_quality: number;
  career_optionality: number;
  company_platform_value: number;
  similarity_group: string | null;
  location: string;
  department: string | null;
  discovery_url: string | null;
  is_student_role: boolean;
  recommendation: string;
  rank?: number;
  company_internal_rank?: number;
  reason?: string;
  superseded_by?: string | null;
  redundancy_risk?: number;
  duplicates_applied_role?: boolean;
}

export interface CompanyDetail {
  overview: CompanyCard & { name: string };
  top_recommended_roles: DetailRole[];
  all_relevant_roles: DetailRole[];
  student_early_careers: DetailRole[];
  applied_roles: DetailRole[];
  recommended_application_set: {
    limit: number;
    over_limit: boolean;
    already_applied: number;
    notes: string[];
    recommended: DetailRole[];
    excluded: DetailRole[];
  };
  official_sources: {
    roles_with_official_link: number;
    roles_third_party_only: DetailRole[];
  };
  calculation: { calculation_version: string; ranking_formula_version: string };
}

export interface CompareSide {
  job_id: string; title: string; company: string; company_tier: string;
  company_platform_value: number; role_strategic_value: number;
  team_project_quality: number; current_fit: number; career_optionality: number;
  evidence_coverage: number; application_priority: number; role_band: string;
  eligibility: string; apply_url: string | null;
}

export interface InboxDashboard {
  metrics: Record<string, number>;
  top_companies_requiring_action: {
    company_id: string; name: string; tier: string;
    reasons: string[]; best_priority: number;
  }[];
}

export const inbox = {
  byTier: () => get<{ groups: TierGroup[]; note: string }>("/inbox/by-tier"),
  global: (limit = 100) =>
    get<{ items: GlobalRow[]; note: string }>(`/inbox/global?limit=${limit}`),
  company: (id: string) => get<CompanyDetail>(`/inbox/company/${id}`),
  compare: (a: string, b: string) =>
    get<{ a: CompareSide; b: CompareSide; leader: string; explanation: string[] }>(
      `/inbox/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
    ),
  choose: (chosen: string, rejected: string) =>
    post<unknown>("/inbox/compare/choose", {
      chosen_job_id: chosen, rejected_job_id: rejected,
    }),
  dashboard: () => get<InboxDashboard>("/inbox/dashboard"),
  rebuild: () => post<Record<string, unknown>>("/inbox/rebuild", {}),
};
