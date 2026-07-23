import Link from "next/link";

import { ApiError } from "@/app/components/ApiError";
import { Section } from "@/app/components/ScoreBits";
import { api } from "@/lib/api";
import { InboxDashboard, inbox } from "@/lib/inbox";

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
  let inboxData: InboxDashboard | null = null;
  let error: string | null = null;

  try {
    [overview, actions] = await Promise.all([api.overview(), api.actionItems()]);
  } catch (e) {
    error = (e as Error).message;
  }
  try {
    inboxData = await inbox.dashboard();
  } catch {
    inboxData = null; // inbox metrics are additive; the page still works without them
  }

  if (error) return <ApiError error={error} />;

  const t = overview!.totals;
  const m = inboxData?.metrics ?? {};

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-lg font-semibold text-white mb-3">Company Coverage</h1>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="S-tier companies monitored" value={m.s_tier_companies_monitored ?? "—"} />
          <Stat label="A-tier companies monitored" value={m.a_tier_companies_monitored ?? "—"} />
          <Stat
            label="Official source coverage"
            value={
              m.official_source_coverage != null
                ? `${(m.official_source_coverage * 100).toFixed(0)}%`
                : "—"
            }
            hint="roles with an employer-owned link"
          />
          <Stat label="Companies tracked" value={m.total_companies ?? "—"} />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-white mb-2">Opportunities</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat
            label="High-priority roles across tiers"
            value={m.high_priority_roles_across_tiers ?? "—"}
            hint="priority ≥ 80"
          />
          <Stat
            label="Companies with recommendations"
            value={m.companies_with_recommended_applications ?? "—"}
          />
          <Stat
            label="Companies near application limit"
            value={m.companies_near_application_limit ?? "—"}
          />
          <Stat
            label="High-potential unrated companies"
            value={m.high_potential_unrated_companies ?? "—"}
            hint="strong roles, thin company evidence"
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

      {inboxData && inboxData.top_companies_requiring_action.length > 0 && (
        <Section
          title="Top Companies Requiring Action"
          subtitle="Ordered by the strongest role currently open at each company."
        >
          <div className="space-y-2">
            {inboxData.top_companies_requiring_action.map((c) => (
              <div
                key={c.company_id}
                className="flex items-start gap-3 rounded border border-gray-800 bg-black/20 p-3"
              >
                <div className="w-10 text-right">
                  <div className="text-sm text-white">{c.best_priority.toFixed(0)}</div>
                  <div className="text-[10px] text-gray-600">best</div>
                </div>
                <div className="flex-1">
                  <Link
                    href={`/companies/${c.company_id}`}
                    className="text-sm text-white hover:underline"
                  >
                    {c.name}
                  </Link>
                  <span className="text-[11px] text-gray-500 ml-2">Tier {c.tier}</span>
                  <div className="text-[11px] text-gray-400 mt-1">
                    {c.reasons.join(" · ")}
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
