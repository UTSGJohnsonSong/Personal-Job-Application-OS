import { api } from "@/lib/api";

// Data is per-request from the API; never prerender at build time.
export const dynamic = "force-dynamic";

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-panel p-4">
      <div className="text-2xl font-semibold text-white">{value}</div>
      <div className="text-xs text-gray-400 mt-1">{label}</div>
    </div>
  );
}

export default async function DashboardPage() {
  let overview = null;
  let actions = null;
  let error: string | null = null;
  try {
    [overview, actions] = await Promise.all([api.overview(), api.actionItems()]);
  } catch (e) {
    error = (e as Error).message;
  }

  if (error) {
    return (
      <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-4 text-amber-200 text-sm">
        Could not reach the API ({error}). Start it with{" "}
        <code>uvicorn app.main:app --reload</code> in <code>apps/api</code>.
      </div>
    );
  }

  const t = overview!.totals;
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-lg font-semibold text-white mb-3">Overview</h1>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Jobs discovered" value={t.total_jobs} />
          <Stat label="New today" value={t.new_today} />
          <Stat label="Applyable now" value={t.applyable} />
          <Stat label="Submitted" value={t.submitted} />
          <Stat label="Submitted this week" value={t.submitted_this_week} />
          <Stat label="Replied" value={t.replied} />
          <Stat label="Interviews" value={t.interviews} />
          <Stat label="Offers" value={t.offers} />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-white mb-2">Needs your attention</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Stat label="Packets waiting confirmation" value={actions!.packets_waiting_confirmation} />
          <Stat label="Deadlines within 48h" value={actions!.deadlines_within_48h} />
          <Stat label="Submitted >2w, no update" value={actions!.stale_submitted_over_2w} />
        </div>
      </section>

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

      <section>
        <h2 className="text-sm font-semibold text-white mb-2">Conversion</h2>
        <div className="grid grid-cols-3 gap-3">
          <Stat label="Submit → reply" value={`${(overview!.conversion.submit_to_reply * 100).toFixed(0)}%`} />
          <Stat label="Reply → interview" value={`${(overview!.conversion.reply_to_interview * 100).toFixed(0)}%`} />
          <Stat label="Interview → offer" value={`${(overview!.conversion.interview_to_offer * 100).toFixed(0)}%`} />
        </div>
      </section>
    </div>
  );
}
