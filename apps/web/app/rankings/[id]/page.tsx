import { ApiError } from "@/app/components/ApiError";
import Link from "next/link";

import { Chip, Section, eligibilityTone, tierTone } from "@/app/components/ScoreBits";
import { JobExplanation, scoring } from "@/lib/scoring";

export const dynamic = "force-dynamic";

const DIMENSION_LABELS: Record<string, string> = {
  resume_brand_signal: "Global Brand / Resume Signal",
  technical_density: "Technical Domain",
  internship_program_quality: "Internship Program",
  career_optionality: "Career Optionality",
  system_project_scale: "System / Project Scale",
  talent_network: "Talent Network",
  stability: "Stability",
};

const CONTRIB_LABELS: Record<string, string> = {
  company_platform_value: "Company Platform",
  role_strategic_value: "Role Strategic Value",
  team_project_quality: "Team Quality",
  current_candidate_fit: "Current Fit",
  career_optionality: "Career Optionality",
  opportunity_viability: "Opportunity Viability",
};

export default async function RankingDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let d: JobExplanation | null = null;
  let error: string | null = null;
  try {
    d = await scoring.job(id);
  } catch (e) {
    error = (e as Error).message;
  }

  if (error || !d) {
    return <ApiError error={error ?? "unknown error"} />;
  }

  const w = d.why_it_ranks_here;
  const ev = d.evidence_coverage;
  const ci = d.company_intelligence;
  const s = d.scores as Record<string, string | number>;

  return (
    <div className="space-y-5">
      <div>
        <Link href="/inbox" className="text-xs text-gray-500 hover:text-white">
          ← Job Inbox
        </Link>
        <h1 className="text-lg font-semibold text-white mt-2">{d.job.title}</h1>
        <div className="flex gap-1.5 flex-wrap mt-2">
          <Chip label="Eligibility" value={String(s.eligibility ?? "—")}
                tone={eligibilityTone(String(s.eligibility))} />
          <Chip label="Company Tier" value={ci.display_tier} tone={tierTone(ci.display_tier)} />
          <Chip label="Role" value={`${d.role_classification.final_category} · ${d.role_classification.role_type}`} />
          <Chip label="" value={String(s.recommendation ?? "")} tone="info" />
        </div>
      </div>

      {/* ---- 1. Why It Ranks Here ---- */}
      <Section
        title="Why It Ranks Here"
        subtitle="Every point in the final priority, accounted for. A plain weighted sum of six independent dimensions — no tier bonus, no priority floor; company standing is captured once, in Company Platform's own weight."
      >
        <div className="space-y-1">
          {Object.entries(w.contributions).map(([k, v]) => (
            <div key={k} className="flex justify-between text-xs">
              <span className="text-gray-400">{CONTRIB_LABELS[k] ?? k}</span>
              <span className="text-gray-200">+{v.toFixed(1)}</span>
            </div>
          ))}
          <div className="border-t border-gray-800 my-2" />
          <div className="flex justify-between text-sm font-semibold">
            <span className="text-white">Final Application Priority</span>
            <span className="text-white">{w.final_priority.toFixed(1)} / 100</span>
          </div>
          <p className="text-[11px] text-gray-500 mt-2">Rule: {w.rule}</p>
          <div className="border-t border-gray-800 my-2" />
          <p className="text-[11px] text-gray-500">
            Not part of the score — day-planning only:
          </p>
          <div className="flex justify-between text-xs">
            <span className="text-gray-400">Action Urgency</span>
            <span className="text-gray-300">{w.action_urgency}</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-gray-400">Est. Application Effort</span>
            <span className="text-gray-300">{w.application_effort_minutes} min</span>
          </div>
        </div>
      </Section>

      {/* ---- 2. Evidence Coverage ---- */}
      <Section
        title="Evidence Coverage"
        subtitle="What is known, what is not, and what is only a prior. Coverage qualifies confidence — it never rewrites the tier letter."
      >
        <div className="grid grid-cols-2 gap-4 text-xs">
          <div>
            <div className="text-gray-400">Overall coverage</div>
            <div className="text-gray-100">{(ev.overall * 100).toFixed(0)}%</div>
            <div className="text-gray-400 mt-2">Company coverage</div>
            <div className="text-gray-100">
              {(ev.company_coverage * 100).toFixed(0)}% · {ev.rating_status}
            </div>
            <div className="text-gray-400 mt-2">Fit coverage</div>
            <div className="text-gray-100">
              {(ev.fit_coverage * 100).toFixed(0)}%
              {ev.fit_known_evidence != null &&
                ` (known-evidence ${ev.fit_known_evidence.toFixed(0)})`}
            </div>
          </div>
          <div>
            <div className="text-emerald-400">Known from evidence</div>
            {ev.known.length === 0 && <div className="text-gray-600">none</div>}
            {ev.known.map((k) => (
              <div key={k} className="text-gray-300">✓ {DIMENSION_LABELS[k] ?? k}</div>
            ))}
            <div className="text-amber-400 mt-2">Unknown — needs research</div>
            {ev.unknown.length === 0 && <div className="text-gray-600">none</div>}
            {ev.unknown.map((k) => (
              <div key={k} className="text-gray-500">? {DIMENSION_LABELS[k] ?? k}</div>
            ))}
          </div>
        </div>
        {ev.notes.map((n) => (
          <p key={n} className="text-[11px] text-amber-300 mt-2">{n}</p>
        ))}
        {ev.unknowns.map((u) => (
          <p key={u} className="text-[11px] text-gray-500 mt-1">• {u}</p>
        ))}
      </Section>

      {/* ---- 3. Company Intelligence ---- */}
      <Section
        title="Company Intelligence"
        subtitle="Tier comes from graded evidence, never from model impressions. Grade-C (anonymous) sources feed the risk radar only."
      >
        <div className="flex gap-1.5 flex-wrap mb-3">
          <Chip label="Estimated Tier" value={ci.estimated_tier} tone={tierTone(ci.estimated_tier)} />
          <Chip label="Rated Tier" value={ci.rated_tier ?? "not yet rated"}
                tone={ci.rated_tier ? "good" : "warn"} />
          <Chip label="Status" value={ci.rating_status} />
          <Chip label="Evidence score" value={ci.known_evidence_score.toFixed(0)} />
        </div>
        <div className="space-y-1">
          {ci.dimensions.map((dim) => (
            <div key={dim.dimension} className="flex justify-between text-xs">
              <span className="text-gray-400">
                {DIMENSION_LABELS[dim.dimension] ?? dim.dimension}
              </span>
              <span className={dim.score == null ? "text-gray-600" : "text-gray-200"}>
                {dim.score == null
                  ? "unknown"
                  : `${(dim.score * 100).toFixed(0)} (conf ${(dim.confidence * 100).toFixed(0)}%, ${dim.evidence_count} src)`}
              </span>
            </div>
          ))}
        </div>
        {ci.risk && ci.risk.level !== "none" && (
          <div className="mt-3 border-t border-gray-800 pt-2">
            <div className="text-xs text-amber-300">
              Risk radar: {ci.risk.level} ({ci.risk.signal_count} anonymous signals,
              quality {ci.risk.evidence_quality}) — not included in the score
            </div>
            {ci.risk.manual_research_required && (
              <div className="text-xs text-red-300 mt-1">Manual research required.</div>
            )}
            {ci.risk.flags.map((f) => (
              <div key={f} className="text-[11px] text-gray-500">• {f}</div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
