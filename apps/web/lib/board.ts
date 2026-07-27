// Data for the board: one flat priority-ordered list of roles, and the company
// register behind it.
//
// Two views over one dataset, deliberately. `/inbox/global` orders roles by
// Application Priority and nothing else — tier is shown but never groups or
// caps it. `/pool` groups the same companies by tier, which is how you decide
// how much of your application budget an employer gets. Mixing the two axes is
// the thing app/company/portfolio.py exists to prevent.
import { API, apiHeaders } from "@/lib/pool";

async function get<T>(path: string, revalidate?: number): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: apiHeaders(),
    // Postings and the queue must be current; the employer register is compiled
    // into the API and only moves when someone edits profiles.py, so re-fetching
    // it on every navigation buys nothing and costs a round trip.
    ...(revalidate ? { next: { revalidate } } : { cache: "no-store" as const }),
  });
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

interface RegistryCard {
  key: string; name: string; tier?: string; platform_tier: string;
  posture: Posture; score?: number; priority_score?: number;
  value_score: number; access_score: number; why?: string; safety_net?: boolean;
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

  /**
   * Every company in the register, not only the ones hiring today.
   *
   * Read from /registry/companies rather than /pool. Both return all 262, but
   * /pool reaches that answer by scanning every posting in the database to
   * attach live role counts — 1.63s against ~11k rows — and the board does not
   * need those counts to draw a tier, a posture or a value/reach pair. The
   * registry endpoint is compiled-in data and answers in 0.24s.
   */
  register: async (): Promise<RegisterCompany[]> => {
    const d = await get<{ groups: { tier: string; companies: RegistryCard[] }[] }>(
      "/registry/companies",
      300,
    );
    return d.groups.flatMap((g) =>
      g.companies.map((c) => ({
        key: c.key,
        name: c.name,
        tier: c.tier ?? g.tier,
        platform_tier: c.platform_tier,
        posture: c.posture,
        score: c.score ?? c.priority_score ?? 0,
        value: c.value_score,
        access: c.access_score,
        why: c.why ?? "",
        safety_net: !!c.safety_net,
        // Live counts belong to /pool. The employers view fills these from the
        // ranked roles it already has, so nothing here claims a number it did
        // not measure.
        open_roles: 0,
        total_roles: 0,
        canada_roles: 0,
        source_status: "",
        careers_url: null,
      })),
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
