import Link from "next/link";

import { Chip, Metric, eligibilityTone, tierTone } from "@/app/components/ScoreBits";
import { recomputeScores } from "@/app/actions";
import { ScoredJob, scoring } from "@/lib/scoring";

export const dynamic = "force-dynamic";

function headline(j: ScoredJob): string {
  // One core explanation: say WHY it ranks here, not "x% match".
  const platform = j.company_platform_value ?? 0;
  const fit = j.current_candidate_fit ?? 0;
  if (j.eligibility === "FAIL") return "Excluded: you are not eligible for this role.";
  if (j.eligibility === "REVIEW") return "Needs manual review before it can be ranked.";
  if (platform > fit + 10) {
    return "Priority comes mainly from company platform and role transferability — not from a perfect skill match.";
  }
  if (fit > platform + 10) {
    return "Priority comes mainly from your current skill fit; company platform evidence is weaker.";
  }
  return "Priority is balanced across platform, role transferability and current fit.";
}

function JobCard({ j }: { j: ScoredJob }) {
  if (!j.scored) {
    return (
      <div className="rounded-lg border border-gray-800 bg-panel p-4">
        <div className="text-white">{j.title}</div>
        <div className="text-[11px] text-amber-400 mt-1">
          Not scored yet — run Recompute.
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-gray-800 bg-panel p-4">
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <Link href={`/rankings/${j.job_id}`} className="text-white hover:underline">
            {j.title}
          </Link>
          <div className="flex gap-1.5 flex-wrap mt-2">
            <Chip label="Eligibility" value={j.eligibility ?? "—"}
                  tone={eligibilityTone(j.eligibility)} />
            <Chip label="Company Tier" value={j.company_tier ?? "—"}
                  tone={tierTone(j.company_tier)} />
            <Chip label="Role" value={`${j.role_category ?? "—"} · ${j.role_type ?? ""}`} />
            <Chip label="Coverage"
                  value={j.evidence_coverage != null
                    ? `${(j.evidence_coverage * 100).toFixed(0)}%` : "—"}
                  tone={(j.evidence_coverage ?? 0) < 0.65 ? "warn" : "mute"} />
            <Chip label="" value={j.recommendation ?? "—"} tone="info" />
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-2xl font-semibold text-white">
            {j.application_priority?.toFixed(0) ?? "—"}
          </div>
          <div className="text-[10px] text-gray-500">Application Priority /100</div>
          <div className="text-[10px] text-gray-600">(not a match %)</div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
        <Metric label="Company Platform" value={j.company_platform_value} />
        <Metric label="Role Strategic Value" value={j.role_strategic_value} />
        <Metric label="Current Fit" value={j.current_candidate_fit} />
        <Metric label="Team Quality" value={j.team_project_quality} />
      </div>

      <p className="text-[11px] text-gray-400 mt-3">{headline(j)}</p>

      <div className="flex gap-3 mt-2">
        <Link href={`/rankings/${j.job_id}`}
              className="text-[11px] text-accent hover:underline">
          Why it ranks here →
        </Link>
        {j.apply_url && (
          <a href={j.apply_url} target="_blank" rel="noreferrer"
             className="text-[11px] text-gray-400 hover:text-white">
            Official application link ↗
          </a>
        )}
      </div>
    </div>
  );
}

export default async function RankingsPage() {
  let items: ScoredJob[] = [];
  let error: string | null = null;
  try {
    items = (await scoring.jobs()).items;
  } catch (e) {
    error = (e as Error).message;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-white">Rankings</h1>
          <p className="text-[11px] text-gray-500 mt-1">
            Eligibility is a gate, not a score. Priority is 0-100 — it is not a match percentage.
          </p>
        </div>
        <form action={recomputeScores}>
          <button className="text-xs px-3 py-1.5 rounded border border-gray-700 text-gray-300 hover:border-accent hover:text-accent">
            Recompute
          </button>
        </form>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-4 text-amber-200 text-sm">
          Could not load rankings ({error}).
        </div>
      )}

      {!error && items.length === 0 && (
        <p className="text-sm text-gray-400">No jobs yet.</p>
      )}

      <div className="grid gap-3">
        {items.map((j) => <JobCard key={j.job_id} j={j} />)}
      </div>

      {items.length >= 2 && (
        <p className="text-[11px] text-gray-500">
          Compare two jobs:{" "}
          <Link
            href={`/compare?a=${items[0].job_id}&b=${items[1].job_id}`}
            className="text-accent hover:underline"
          >
            {items[0].title} vs {items[1].title}
          </Link>
        </p>
      )}
    </div>
  );
}
