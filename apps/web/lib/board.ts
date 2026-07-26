// Data for the board: one flat priority-ordered list of roles, and the company
// register behind it.
//
// Two views over one dataset, deliberately. `/inbox/global` orders roles by
// Application Priority and nothing else — tier is shown but never groups or
// caps it. `/pool` groups the same companies by tier, which is how you decide
// how much of your application budget an employer gets. Mixing the two axes is
// the thing app/company/portfolio.py exists to prevent.
import { API, apiHeaders } from "@/lib/pool";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store", headers: apiHeaders() });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

/** One role in the global queue. Ordered by application_priority alone. */
export interface GlobalRole {
  global_rank: number;
  company_id: string;
  company: string;
  company_tier: string;
  company_platform_value: number;
  job_id: string;
  title: string;
  role_band: string | null;
  role_type: string | null;
  eligibility: string;
  application_priority: number;
  role_strategic_value: number;
  current_fit: number;
  evidence_coverage: number;
  recommendation: string;
  is_official: boolean;
  apply_url: string | null;
  location: string;
  other_locations: string[];
}

/**
 * What to DO about an employer, which a tier cannot express.
 *
 * A tier is sqrt(value x access), so a company that is worth a great deal and
 * is hard to reach scores LOW — every "worth forcing" employer in the register
 * lands in C or D. Ordering the page by tier is therefore exactly what hides
 * them, and they are the ones where a cold application is close to wasted.
 */
export type Posture = "balanced" | "floor_only" | "worth_forcing";

export interface RegisterCompany {
  key: string;
  name: string;
  tier: string;
  platform_tier: string;
  posture: Posture;
  score: number;
  value: number;
  access: number;
  why: string;
  open_roles: number;
  total_roles: number;
  canada_roles: number;
  safety_net: boolean;
  source_status: string;
  careers_url: string | null;
}

/** The six weighted dimensions, fetched only when a row is opened. */
export interface RoleDetail {
  job: { id: string; title: string; apply_url: string | null };
  scores: Record<string, unknown>;
  why_it_ranks_here: {
    contributions: Record<string, number>;
    final_priority: number;
    action_urgency?: string;
    application_effort_minutes?: number;
    rule?: string;
  };
  evidence_coverage: { overall?: number; known?: string[]; unknown?: string[] };
}

interface PoolCard {
  key: string; name: string; platform_tier: string; posture: Posture;
  score: number; value: number; access: number; why: string;
  open_roles: number; total_roles: number; canada_roles: number;
  safety_net: boolean; source_status: string; careers_url: string | null;
}

export const board = {
  /** Priority-ordered roles. `limit` is the API's own cap (<=500). */
  roles: async (limit = 300): Promise<GlobalRole[]> => {
    const d = await get<{ items: GlobalRole[] }>(`/inbox/global?limit=${limit}`);
    return d.items ?? [];
  },

  /**
   * Job ids already on the apply list, so the board reflects a decision that
   * was made on a previous visit. Without this the list lives in browser
   * memory and a reload silently throws away everything you picked.
   */
  queuedJobIds: async (): Promise<string[]> => {
    const d = await get<{ items?: { job_id: string }[] } | { job_id: string }[]>("/queue");
    const items = Array.isArray(d) ? d : (d.items ?? []);
    return items.map((i) => i.job_id);
  },

  /** Every company in the register, not only the ones hiring today. */
  register: async (): Promise<RegisterCompany[]> => {
    const d = await get<{ groups: { tier: string; companies: PoolCard[] }[] }>("/pool");
    return d.groups.flatMap((g) =>
      g.companies.map((c) => ({ ...c, tier: g.tier }))
    );
  },

  detail: (jobId: string) => get<RoleDetail>(`/scoring/jobs/${jobId}`),
};

/** Human labels. The register stores machine values; the screen shows English. */
export const POSTURE_LABEL: Record<Posture, string> = {
  balanced: "",
  floor_only: "Fallback",
  worth_forcing: "Refer in",
};

export const POSTURE_HELP: Record<Posture, string> = {
  balanced: "",
  floor_only:
    "Reachable but low value. Worth having, never worth displacing a real target.",
  worth_forcing:
    "Worth far more than it is reachable. A cold application here is close to wasted — a referral or a direct conversation is the move.",
};

/** Canada-reachability, derived from the location string the gate judged. */
export function reachOf(loc: string): "ca" | "intl" | "unknown" {
  const l = (loc || "").toLowerCase();
  if (!l || l === "n/a" || /^\d+\s+locations?$/.test(l) || l === "in-office") return "unknown";
  if (/canada|toronto|ontario|ottawa|vancouver|montr|waterloo|calgary|mississauga|oakville|quebec|alberta|british columbia/.test(l))
    return "ca";
  return "intl";
}
