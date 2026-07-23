import Link from "next/link";

import { rebuildInbox } from "@/app/actions";
import { ApiError } from "@/app/components/ApiError";
import { Chip, eligibilityTone } from "@/app/components/ScoreBits";
import { CompanyCard, TierGroup, inbox } from "@/lib/inbox";

export const dynamic = "force-dynamic";

const TIER_STYLE: Record<string, string> = {
  S: "border-emerald-700 text-emerald-300",
  A: "border-blue-700 text-blue-300",
  B: "border-gray-600 text-gray-300",
  C: "border-gray-700 text-gray-400",
  D: "border-gray-800 text-gray-500",
};

function tierStyle(tier: string): string {
  return TIER_STYLE[tier] ?? "border-amber-700 text-amber-300";
}

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${(v * 100).toFixed(0)}%`;
}

function Card({ c }: { c: CompanyCard }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-panel p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            href={`/companies/${c.company_id}`}
            className="text-white font-medium hover:underline"
          >
            {c.name}
          </Link>
          <div className="flex gap-1.5 flex-wrap mt-2">
            <Chip label="Tier" value={c.tier_display} />
            <Chip label="Platform" value={c.platform_value.toFixed(0)} />
            <Chip
              label="Evidence"
              value={pct(c.evidence_coverage)}
              tone={c.evidence_coverage < 0.65 ? "warn" : "mute"}
            />
            <Chip
              label="Official src"
              value={pct(c.official_source_coverage)}
              tone={c.official_source_coverage < 1 ? "warn" : "good"}
            />
            {c.high_potential_unrated && (
              <Chip label="" value="High potential — needs research" tone="warn" />
            )}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-xs text-gray-400">Recommended</div>
          <div className="text-2xl font-semibold text-white">{c.recommended_count}</div>
          <div className="text-[10px] text-gray-600">
            {c.submitted_applications} submitted
          </div>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-2 mt-3 text-center">
        {[
          ["Open", c.total_open_roles],
          ["Canada", c.canada_roles],
          ["GTA", c.gta_roles],
          ["Student", c.student_roles],
          ["Relevant", c.relevant_roles],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded border border-gray-800 py-1">
            <div className="text-sm text-gray-100">{value as number}</div>
            <div className="text-[10px] text-gray-500">{label as string}</div>
          </div>
        ))}
      </div>

      {c.top_roles.length > 0 && (
        <div className="mt-3 space-y-1">
          <div className="text-[11px] text-gray-500">
            Top recommended roles (priority orders roles, not tier)
          </div>
          {c.top_roles.map((r) => (
            <div key={r.job_id} className="flex items-center gap-2 text-xs">
              <span className="w-9 text-right text-white font-medium">
                {r.application_priority.toFixed(0)}
              </span>
              <span className="text-gray-300 truncate flex-1">{r.title}</span>
              <Chip label="" value={r.role_band} />
              <Chip label="" value={r.eligibility} tone={eligibilityTone(r.eligibility)} />
              {!r.is_official && <Chip label="" value="no official link" tone="warn" />}
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-3 mt-3 text-[11px]">
        <Link href={`/companies/${c.company_id}`} className="text-accent hover:underline">
          Company detail →
        </Link>
        {c.last_synced_at && (
          <span className="text-gray-600">
            synced {new Date(c.last_synced_at).toLocaleDateString()}
          </span>
        )}
      </div>
    </div>
  );
}

function Group({ g }: { g: TierGroup }) {
  return (
    <section>
      <div className="flex items-baseline gap-3 mb-2">
        <span
          className={`text-sm font-semibold px-2 py-0.5 rounded border ${tierStyle(g.tier)}`}
        >
          {g.tier}
        </span>
        <span className="text-[11px] text-gray-500">
          {g.company_count} companies · {g.role_count} relevant roles
        </span>
      </div>
      <div className="grid gap-3">
        {g.companies.map((c) => (
          <Card key={c.company_id} c={c} />
        ))}
      </div>
    </section>
  );
}

export default async function CompaniesPage() {
  let groups: TierGroup[] = [];
  let error: string | null = null;
  try {
    groups = (await inbox.byTier()).groups;
  } catch (e) {
    error = (e as Error).message;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-white">Companies by Tier</h1>
          <p className="text-[11px] text-gray-500 mt-1">
            Tier organises companies. Application Priority (0-100) orders roles — an
            A-tier role can outrank an S-tier one.
          </p>
        </div>
        <form action={rebuildInbox}>
          <button className="text-xs px-3 py-1.5 rounded border border-gray-700 text-gray-300 hover:border-accent hover:text-accent">
            Rebuild
          </button>
        </form>
      </div>

      {error && <ApiError error={error} />}
      {!error && groups.length === 0 && (
        <p className="text-sm text-gray-400">
          No scored companies yet. Run Recompute on Rankings, then Rebuild here.
        </p>
      )}

      {groups.map((g) => (
        <Group key={g.tier} g={g} />
      ))}
    </div>
  );
}
