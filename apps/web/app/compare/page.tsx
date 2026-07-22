import { recordPreference } from "@/app/actions";
import { Chip, Metric, eligibilityTone, tierTone } from "@/app/components/ScoreBits";
import { ScoredJob, scoring } from "@/lib/scoring";

export const dynamic = "force-dynamic";

function Column({ j, other }: { j: ScoredJob; other: ScoredJob }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-panel p-4 flex-1">
      <div className="text-white text-sm">{j.title}</div>
      <div className="text-3xl font-semibold text-white mt-2">
        {j.application_priority?.toFixed(0) ?? "—"}
      </div>
      <div className="text-[10px] text-gray-500 mb-3">Application Priority /100</div>

      <div className="flex gap-1.5 flex-wrap mb-3">
        <Chip label="Eligibility" value={j.eligibility ?? "—"} tone={eligibilityTone(j.eligibility)} />
        <Chip label="Tier" value={j.company_tier ?? "—"} tone={tierTone(j.company_tier)} />
        <Chip label="Role" value={j.role_category ?? "—"} />
      </div>

      <div className="space-y-2">
        <Metric label="Company Platform" value={j.company_platform_value} />
        <Metric label="Role Strategic Value" value={j.role_strategic_value} />
        <Metric label="Current Fit" value={j.current_candidate_fit} />
        <Metric label="Team Quality" value={j.team_project_quality} />
        <Metric label="Career Optionality" value={j.career_optionality} />
        <Metric
          label="Evidence Coverage"
          value={j.evidence_coverage != null ? j.evidence_coverage * 100 : null}
        />
      </div>

      {j.why && j.why.length > 0 && (
        <p className="text-[11px] text-emerald-400 mt-3">✓ {j.why[0]}</p>
      )}
      {j.why_not && j.why_not.length > 0 && (
        <p className="text-[11px] text-amber-400 mt-1">! {j.why_not[0]}</p>
      )}

      <form action={recordPreference} className="mt-4">
        <input type="hidden" name="chosen" value={j.job_id} />
        <input type="hidden" name="rejected" value={other.job_id} />
        <button className="w-full text-xs px-3 py-2 rounded bg-accent text-white hover:opacity-90">
          I would apply to this one
        </button>
      </form>
    </div>
  );
}

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ a?: string; b?: string }>;
}) {
  const sp = await searchParams;
  if (!sp.a || !sp.b) {
    return (
      <p className="text-sm text-gray-400">
        Pick two jobs to compare from the Rankings page.
      </p>
    );
  }

  let a: ScoredJob | null = null;
  let b: ScoredJob | null = null;
  let error: string | null = null;
  try {
    const res = await scoring.compare(sp.a, sp.b);
    a = res.a;
    b = res.b;
  } catch (e) {
    error = (e as Error).message;
  }

  if (error || !a || !b) {
    return (
      <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-4 text-amber-200 text-sm">
        Could not compare ({error}).
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-white">Compare</h1>
        <p className="text-[11px] text-gray-500 mt-1">
          Your choice is recorded as a pairwise preference. It calibrates how much
          platform value you are willing to trade for current fit. Nothing is
          applied to the weights automatically.
        </p>
      </div>
      <div className="flex flex-col md:flex-row gap-3">
        <Column j={a} other={b} />
        <Column j={b} other={a} />
      </div>
    </div>
  );
}
