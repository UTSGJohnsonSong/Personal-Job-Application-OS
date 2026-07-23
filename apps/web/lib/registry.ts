// Client for the company registry — the tiering layer.
//
// The registry is a frozen assessment rather than accumulated data, so these
// reads are stateless and never depend on a sync having run.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const API_TOKEN = process.env.API_TOKEN || "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: API_TOKEN
      ? { Authorization: `Bearer ${API_TOKEN}`, "Content-Type": "application/json" }
      : { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export type RegistryView = "apply" | "value" | "platform";
export type Posture = "balanced" | "worth_forcing" | "floor_only";
export type ValueAction =
  | "referral_or_outreach"
  | "already_in_apply_queue"
  | "watch";

export interface RegistryInputs {
  brand_ca: number;
  brand_us: number;
  brand_cn: number;
  tech: number;
  depth: number;
  role: number;
  domain: number;
  founder: number;
  program: number;
}

export type SourceStatus = "verified" | "partial" | "manual_only" | "searching";

export interface RegistrySource {
  status: SourceStatus;
  automatable: boolean;
  careers_url: string | null;
  connector: string | null;
  observed_jobs: number | null;
  observed_canada: number | null;
  observed_student_canada: number | null;
  note: string | null;
  probed_on: string | null;
}

export interface RegistryCompany {
  key: string;
  name: string;
  tier: string;
  score: number;
  value_score: number;
  access_score: number;
  priority_score: number;
  platform_score: number;
  value_tier: string;
  platform_tier: string;
  priority_tier: string;
  posture: Posture;
  action: ValueAction;
  worth_taking_if_offered: boolean;
  safety_net: boolean;
  role_floor: boolean;
  adjusted: boolean;
  override_reason: string | null;
  why: string;
  tags: string[];
  source: RegistrySource;
  inputs: RegistryInputs;
  assessed_on: string;
  valid_until: string;
}

export interface RegistryGroup {
  tier: string;
  count: number;
  companies: RegistryCompany[];
}

export interface RegistryList {
  view: RegistryView;
  total: number;
  groups: RegistryGroup[];
  counts: Record<string, number>;
}

export interface RegistryMeta {
  total_rated: number;
  counts: Record<string, Record<string, number>>;
  bands: Record<string, { floor: number; tier: string }[]>;
  offer_accept_threshold: number;
  formulas: Record<string, string>;
  adjustments: {
    name: string;
    algo_priority_tier: string;
    final_priority_tier: string;
    algo_platform_tier: string;
    final_platform_tier: string;
    reason: string | null;
  }[];
  excluded_categories: Record<string, string>;
  gated_categories: Record<string, { gate: string; reason: string }>;
  source_coverage: {
    with_known_board: number;
    without_source: number;
    by_status: Record<string, number>;
  };
}

export interface RegistryDetail extends RegistryCompany {
  breakdown: {
    brand: number;
    value_terms: Record<string, number>;
    access_terms: Record<string, number>;
    platform_terms: Record<string, number>;
    algo_platform_tier: string;
    algo_priority_tier: string;
  };
}

export const registry = {
  companies: (params?: { view?: RegistryView; tier?: string; posture?: string }) => {
    const qs = new URLSearchParams(
      Object.entries(params ?? {}).filter(([, v]) => v) as [string, string][],
    ).toString();
    return get<RegistryList>(`/registry/companies${qs ? `?${qs}` : ""}`);
  },
  company: (key: string) => get<RegistryDetail>(`/registry/company/${key}`),
  meta: () => get<RegistryMeta>("/registry/meta"),
};

// ---------------------------------------------------------------------------
// Presentation vocabulary. Kept beside the client so the wording that explains
// a view never drifts from the data it labels.
// ---------------------------------------------------------------------------
export const VIEWS: {
  id: RegistryView;
  label: string;
  question: string;
  formula: string;
}[] = [
  {
    id: "apply",
    label: "Apply Queue",
    question: "Where should applications actually go?",
    formula: "√(value × access)",
  },
  {
    id: "value",
    label: "Value",
    question: "What is worth wanting, however hard to reach?",
    formula: "value only — access deliberately ignored",
  },
  {
    id: "platform",
    label: "Platform",
    question: "How strong is the company on its own terms?",
    formula: "72×brand + 16×programme + 4×engineering",
  },
];

export const ACTION_COPY: Record<ValueAction, { text: string; tone: string }> = {
  referral_or_outreach: {
    text: "Referral or outreach — a cold application will not reach this",
    tone: "warn",
  },
  already_in_apply_queue: { text: "Also in the apply queue", tone: "good" },
  watch: { text: "Watch only", tone: "mute" },
};

// A company we cannot reach automatically is still a company to apply to.
// Labelling that plainly is what stops connector coverage from quietly
// deciding which employers exist.
export const SOURCE_COPY: Record<SourceStatus, { text: string; tone: string }> = {
  verified: { text: "Source verified", tone: "good" },
  partial: { text: "Partial board — absence proves nothing", tone: "warn" },
  manual_only: { text: "Apply manually — no automatable feed", tone: "info" },
  searching: { text: "No source located yet", tone: "bad" },
};

export const POSTURE_COPY: Record<Posture, string> = {
  worth_forcing: "Worth more than it is reachable",
  floor_only: "Reachable but low value — floor option",
  balanced: "Balanced",
};
