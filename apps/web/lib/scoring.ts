// v2 scoring client. `application_priority` is a 0-100 PRIORITY, never a match %.
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

export interface ScoredJob {
  job_id: string;
  title: string;
  apply_url: string | null;
  freshness: number | null;
  scored: boolean;
  eligibility?: string;
  company_tier?: string;
  company_platform_value?: number;
  role_category?: string;
  role_type?: string;
  role_strategic_value?: number;
  current_candidate_fit?: number;
  team_project_quality?: number;
  career_optionality?: number;
  evidence_coverage?: number;
  application_priority?: number;
  opportunity_estimate?: string;
  recommendation?: string;
  interaction_rule?: string;
  why?: string[];
  why_not?: string[];
  unknowns?: string[];
}

export interface JobExplanation {
  job: { id: string; title: string; apply_url: string | null; description: string | null };
  scores: Record<string, unknown>;
  why_it_ranks_here: {
    base_priority: number;
    contributions: Record<string, number>;
    tier_adjustment: number;
    urgency_adjustment: number;
    floor_applied: boolean;
    final_priority: number;
    rule: string;
  };
  evidence_coverage: {
    overall: number;
    company_coverage: number;
    rating_status: string;
    fit_coverage: number;
    fit_known_evidence: number | null;
    known: string[];
    unknown: string[];
    notes: string[];
    unknowns: string[];
  };
  company_intelligence: {
    estimated_tier: string;
    rated_tier: string | null;
    display_tier: string;
    rating_status: string;
    known_evidence_score: number;
    conservative_score: number;
    dimensions: {
      dimension: string; score: number | null; confidence: number;
      evidence_count: number; evidence: string[];
    }[];
    risk: {
      level: string; evidence_quality: string; signal_count: number;
      manual_research_required: boolean; flags: string[];
    } | null;
  };
  role_classification: { final_category: string; role_type: string };
}

export const scoring = {
  jobs: () => get<{ count: number; items: ScoredJob[]; note: string }>("/scoring/jobs"),
  job: (id: string) => get<JobExplanation>(`/scoring/jobs/${id}`),
  compare: (a: string, b: string) =>
    get<{ a: ScoredJob; b: ScoredJob }>(
      `/scoring/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
    ),
  recompute: (mode = "internship") => post<unknown>("/scoring/recompute", { mode }),
  preference: (chosen: string, rejected: string) =>
    post<unknown>("/scoring/preference", {
      chosen_job_id: chosen, rejected_job_id: rejected,
    }),
};
