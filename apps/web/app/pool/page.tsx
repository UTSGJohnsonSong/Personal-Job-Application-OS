import { ApiError } from "@/app/components/ApiError";
import { RefreshButton } from "@/app/pool/RefreshButton";
import { TierSection } from "@/app/pool/TierSection";
import { Pool, pool } from "@/lib/pool";

export const dynamic = "force-dynamic";

export default async function PoolPage() {
  let data: Pool | null = null;
  let estimate = { sources: 0, estimated_seconds: 0 };
  let error: string | null = null;
  try {
    const [p, e] = await Promise.all([pool.get(), pool.estimate()]);
    data = p;
    estimate = e;
  } catch (e) {
    error = (e as Error).message;
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-lg font-semibold text-white">Application Pool</h1>
          <p className="text-[11px] text-gray-500 mt-1">
            {data
              ? `${data.total_companies} companies · ${data.total_open_roles} open roles you can apply to`
              : "Companies grouped by tier; roles ordered within each company."}
          </p>
        </div>
        <RefreshButton
          estimatedSeconds={estimate.estimated_seconds}
          sources={estimate.sources}
          lastRefreshed={data?.last_refreshed ?? null}
        />
      </div>

      {error && <ApiError error={error} />}

      {data && (
        <div className="space-y-4">
          {data.groups.map((g) => (
            <TierSection
              key={g.tier}
              group={g}
              // S and A open by default: those are where applications go. The
              // long tail stays collapsed so the page opens on what matters.
              defaultOpen={g.tier === "S" || g.tier === "A"}
            />
          ))}
        </div>
      )}
    </div>
  );
}
