import Link from "next/link";

import { chooseRole } from "@/app/actions";
import { ApiError } from "@/app/components/ApiError";
import { Chip, Metric, Section, eligibilityTone } from "@/app/components/ScoreBits";
import { CompareSide, GlobalRow, inbox } from "@/lib/inbox";

export const dynamic = "force-dynamic";

function pct(v: number): string {
  return `${(v * 100).toFixed(0)}%`;
}

function Row({ r, compareWith }: { r: GlobalRow; compareWith: string | null }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-panel p-3">
      <div className="flex items-start gap-3">
        <div className="text-gray-500 text-xs w-6 pt-1">#{r.global_rank}</div>
        <div className="flex-1 min-w-0">
          <div className="text-sm text-white">{r.title}</div>
          <div className="text-[11px] text-gray-400">
            <Link href={`/companies/${r.company_id}`} className="hover:underline">
              {r.company}
            </Link>
          </div>
          <div className="flex gap-1.5 flex-wrap mt-1.5">
            <Chip label="Tier" value={r.company_tier} />
            <Chip label="Eligibility" value={r.eligibility} tone={eligibilityTone(r.eligibility)} />
            <Chip label="Role" value={r.role_band} />
            <Chip label="Evidence" value={pct(r.evidence_coverage)}
                  tone={r.evidence_coverage < 0.65 ? "warn" : "mute"} />
            {r.recommendation && <Chip label="" value={r.recommendation} tone="info" />}
            {!r.is_official && <Chip label="" value="no official link" tone="warn" />}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-2xl font-semibold text-white">
            {r.application_priority.toFixed(0)}
          </div>
          <div className="text-[10px] text-gray-500">Priority /100</div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 mt-2">
        <Metric label="Platform" value={r.company_platform_value} />
        <Metric label="Role Strategic" value={r.role_strategic_value} />
        <Metric label="Current Fit" value={r.current_fit} />
      </div>

      <div className="flex gap-3 mt-2 text-[11px]">
        {r.apply_url && (
          <a href={r.apply_url} target="_blank" rel="noreferrer"
             className="text-accent hover:underline">Official application ↗</a>
        )}
        <Link href={`/rankings/${r.job_id}`} className="text-gray-400 hover:text-white">
          Why it ranks here →
        </Link>
        {compareWith && compareWith !== r.job_id ? (
          <Link href={`/priority?compare=${compareWith}&with=${r.job_id}`}
                className="text-blue-300 hover:underline">Compare with selected</Link>
        ) : (
          <Link href={`/priority?compare=${r.job_id}`}
                className="text-gray-400 hover:text-white">Select to compare</Link>
        )}
      </div>
    </div>
  );
}

function CompareColumn({ s, other }: { s: CompareSide; other: CompareSide }) {
  return (
    <div className="flex-1 rounded-lg border border-gray-800 bg-panel p-4">
      <div className="text-sm text-white">{s.title}</div>
      <div className="text-[11px] text-gray-400 mb-2">
        {s.company} · Tier {s.company_tier}
      </div>
      <div className="text-3xl font-semibold text-white">
        {s.application_priority.toFixed(0)}
      </div>
      <div className="text-[10px] text-gray-500 mb-3">Application Priority /100</div>
      <div className="space-y-2">
        <Metric label="Company Platform Value" value={s.company_platform_value} />
        <Metric label="Role Strategic Value" value={s.role_strategic_value} />
        <Metric label="Team / Project Quality" value={s.team_project_quality} />
        <Metric label="Current Fit" value={s.current_fit} />
        <Metric label="Career Optionality" value={s.career_optionality} />
        <Metric label="Evidence Coverage" value={s.evidence_coverage * 100} />
      </div>
      <form action={chooseRole} className="mt-4">
        <input type="hidden" name="chosen" value={s.job_id} />
        <input type="hidden" name="rejected" value={other.job_id} />
        <button className="w-full text-xs px-3 py-2 rounded bg-accent text-white hover:opacity-90">
          I would apply to this one
        </button>
      </form>
    </div>
  );
}

export default async function PriorityPage({
  searchParams,
}: {
  searchParams: Promise<{ compare?: string; with?: string }>;
}) {
  const sp = await searchParams;
  let items: GlobalRow[] = [];
  let error: string | null = null;
  try {
    items = (await inbox.global(100)).items;
  } catch (e) {
    error = (e as Error).message;
  }

  let cmp: Awaited<ReturnType<typeof inbox.compare>> | null = null;
  if (sp.compare && sp.with) {
    try {
      cmp = await inbox.compare(sp.compare, sp.with);
    } catch {
      cmp = null;
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-white">Global Priority</h1>
        <p className="text-[11px] text-gray-500 mt-1">
          Every company, one queue, ordered by Application Priority alone. Tier is
          shown but never groups this list.
        </p>
      </div>

      {error && <ApiError error={error} />}

      {cmp && (
        <Section title="Cross-Tier Compare"
                 subtitle="Your choice is stored as a pairwise preference and calibrates platform-vs-fit.">
          <div className="flex flex-col md:flex-row gap-3">
            <CompareColumn s={cmp.a} other={cmp.b} />
            <CompareColumn s={cmp.b} other={cmp.a} />
          </div>
          <div className="mt-3 rounded border border-gray-800 bg-black/20 p-3">
            <div className="text-[11px] text-gray-400 mb-1">Why they rank this way</div>
            {cmp.explanation.map((e) => (
              <p key={e} className="text-[11px] text-gray-300">• {e}</p>
            ))}
          </div>
        </Section>
      )}

      {sp.compare && !sp.with && (
        <p className="text-[11px] text-blue-300">
          Selected a role to compare. Pick a second one below.
        </p>
      )}

      {!error && items.length === 0 && (
        <p className="text-sm text-gray-400">No scored roles yet.</p>
      )}

      <div className="grid gap-2">
        {items.map((r) => (
          <Row key={r.job_id} r={r} compareWith={sp.compare ?? null} />
        ))}
      </div>
    </div>
  );
}
