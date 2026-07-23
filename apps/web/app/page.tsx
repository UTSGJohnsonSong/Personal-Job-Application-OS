import Link from "next/link";

import { ApiError } from "@/app/components/ApiError";
import { Section } from "@/app/components/ScoreBits";
import { api } from "@/lib/api";
import { Pool, pool } from "@/lib/pool";

// Data is per-request from the API; never prerender at build time.
export const dynamic = "force-dynamic";

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: number | string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-800 bg-panel p-4">
      <div className="text-2xl font-semibold text-white">{value}</div>
      <div className="text-xs text-gray-400 mt-1">{label}</div>
      {hint && <div className="text-[10px] text-gray-600 mt-0.5">{hint}</div>}
    </div>
  );
}

export default async function DashboardPage() {
  let overview = null;
  let actions = null;
  let poolData: Pool | null = null;
  let error: string | null = null;

  try {
    [overview, actions] = await Promise.all([api.overview(), api.actionItems()]);
  } catch (e) {
    error = (e as Error).message;
  }
  try {
    poolData = await pool.get();
  } catch {
    poolData = null; // pool metrics are additive; the page still works without them
  }

  if (error) return <ApiError error={error} />;

  const t = overview!.totals;
  const groups = poolData?.groups ?? [];
  const companies = groups.flatMap((g) =>
    g.companies.map((c) => ({ ...c, tier: g.tier })),
  );
  const hiring = companies.filter((c) => c.open_roles > 0);
  const canadaRoles = companies.reduce((n, c) => n + c.canada_roles, 0);
  const byTier = (tier: string) =>
    groups.find((g) => g.tier === tier)?.company_count ?? 0;

  return (
    <div className="space-y-8">
      <section>
        <div className="flex items-baseline justify-between mb-3">
          <h1 className="text-lg font-semibold text-white">Pool Coverage</h1>
          <Link href="/inbox" className="text-[11px] text-accent hover:underline">
            Open Job Inbox →
          </Link>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="S-tier companies" value={byTier("S") || "—"} />
          <Stat label="A-tier companies" value={byTier("A") || "—"} />
          <Stat
            label="Companies hiring now"
            value={hiring.length || "—"}
            hint="have at least one role you could apply to"
          />
          <Stat
            label="Companies rated"
            value={poolData?.total_companies ?? "—"}
            hint="assessment frozen for the year"
          />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-white mb-2">Opportunities</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat
            label="Open roles you can apply to"
            value={poolData?.total_open_roles ?? "—"}
            hint="eligibility gate passed or needs review"
          />
          <Stat label="Roles in Canada" value={canadaRoles || "—"} />
          <Stat
            label="Sources mapped"
            value={hiring.length ? `${hiring.length} live` : "—"}
            hint="the rest apply manually"
          />
          <Stat
            label="Last refreshed"
            value={
              poolData?.last_refreshed
                ? new Date(poolData.last_refreshed).toLocaleDateString()
                : "—"
            }
          />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-white mb-2">Pipeline</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Jobs discovered" value={t.total_jobs} />
          <Stat label="New today" value={t.new_today} />
          <Stat label="Submitted" value={t.submitted} />
          <Stat
            label="Waiting for confirmation"
            value={actions!.packets_waiting_confirmation}
          />
        </div>
      </section>

      {hiring.length > 0 && (
        <Section
          title="Where to look first"
          subtitle="Highest-tier companies with roles open right now."
        >
          <div className="space-y-2">
            {hiring.slice(0, 6).map((c) => (
              <div
                key={c.key}
                className="flex items-start gap-3 rounded border border-gray-800 bg-black/20 p-3"
              >
                <div className="w-10 text-right shrink-0">
                  <div className="text-sm text-white">{c.score.toFixed(0)}</div>
                  <div className="text-[10px] text-gray-600">tier {c.tier}</div>
                </div>
                <div className="flex-1 min-w-0">
                  <Link
                    href={`/inbox/${c.key}`}
                    className="text-sm text-white hover:underline"
                  >
                    {c.name}
                  </Link>
                  <div className="text-[11px] text-gray-400 mt-0.5">
                    {c.open_roles} open
                    {c.canada_roles > 0 && ` · ${c.canada_roles} in Canada`}
                    {c.top_roles[0] && ` · top: ${c.top_roles[0].title}`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      <section>
        <h2 className="text-sm font-semibold text-white mb-2">Funnel</h2>
        <div className="rounded-lg border border-gray-800 bg-panel p-4 space-y-2">
          {overview!.funnel.map((f) => (
            <div key={f.stage} className="flex items-center gap-3">
              <div className="w-40 text-xs text-gray-400 capitalize">
                {f.stage.replace(/_/g, " ")}
              </div>
              <div className="flex-1 bg-gray-800 rounded h-3 overflow-hidden">
                <div
                  className="bg-accent h-3"
                  style={{ width: `${Math.min(100, f.count * 12 + 4)}%` }}
                />
              </div>
              <div className="w-8 text-right text-xs text-gray-300">{f.count}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
