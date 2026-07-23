import Link from "next/link";

import { ApiError } from "@/app/components/ApiError";
import { Chip, Metric, Section } from "@/app/components/ScoreBits";
import { CompanyPage, PoolRole, eligibilityTone, pool } from "@/lib/pool";

export const dynamic = "force-dynamic";

const INPUT_COPY: Record<string, string> = {
  brand_ca: "Recognition in Canada",
  brand_us: "Recognition in the US",
  brand_cn: "Recognition in China",
  tech: "Engineering reputation",
  depth: "Size of the Canadian technology organisation",
  role: "Availability of roles you could win",
  domain: "Fit with health, fintech or applied ToB AI",
  founder: "Customer contact, sales visibility, equity",
  program: "Maturity of the co-op programme",
};

function date(v: string | null): string {
  return v ? new Date(v).toLocaleDateString() : "—";
}

function RoleRow({ r }: { r: PoolRole }) {
  return (
    <div className="rounded border border-gray-800 px-3 py-2">
      <div className="flex items-baseline gap-2">
        <span className="w-6 text-right text-gray-600 text-xs tabular-nums">
          {r.rank}
        </span>
        <Link
          href={`/rankings/${r.job_id}`}
          className="text-sm text-white hover:text-accent hover:underline flex-1"
        >
          {r.title}
        </Link>
        <span className={`text-[11px] ${eligibilityTone(r.eligibility)}`}>
          {r.eligibility}
        </span>
        <span className="text-sm text-white tabular-nums w-8 text-right">
          {r.priority == null ? "—" : r.priority.toFixed(0)}
        </span>
      </div>
      <div className="flex gap-3 flex-wrap mt-1 pl-8 text-[10px] text-gray-500">
        {r.location && (
          <span className={r.in_canada ? "text-emerald-500" : ""}>{r.location}</span>
        )}
        {r.department && <span>{r.department}</span>}
        {r.role_band && <span>band {r.role_band}</span>}
        {r.role_type && <span>{r.role_type.replace(/_/g, " ")}</span>}
        <span>posted {date(r.posted_at)}</span>
        <span>seen {date(r.first_seen_at)}</span>
        {r.deadline && <span className="text-amber-400">closes {date(r.deadline)}</span>}
        <span>freshness {(r.freshness * 100).toFixed(0)}%</span>
        {r.apply_url && (
          <a
            href={r.apply_url}
            target="_blank"
            rel="noreferrer"
            className="text-accent hover:underline"
          >
            Official application ↗
          </a>
        )}
      </div>
    </div>
  );
}

export default async function PoolCompanyPage({
  params,
}: {
  params: Promise<{ key: string }>;
}) {
  const { key } = await params;
  let c: CompanyPage | null = null;
  let error: string | null = null;
  try {
    c = await pool.company(key);
  } catch (e) {
    error = (e as Error).message;
  }

  if (error || !c) {
    return (
      <div className="space-y-4">
        <Link href="/inbox" className="text-xs text-accent hover:underline">
          ← Job Inbox
        </Link>
        <ApiError error={error ?? "not found"} />
      </div>
    );
  }

  const eligible = c.roles.filter((r) => r.eligibility === "PASS");
  const review = c.roles.filter((r) => r.eligibility === "REVIEW");
  const blocked = c.roles.filter((r) => r.eligibility === "FAIL");

  return (
    <div className="space-y-5">
      <Link href="/inbox" className="text-xs text-accent hover:underline">
        ← Job Inbox
      </Link>

      <div>
        <div className="flex items-baseline gap-3 flex-wrap">
          <h1 className="text-lg font-semibold text-white">{c.name}</h1>
          <Chip label="tier" value={`${c.tier} · ${c.score.toFixed(0)}`} />
          <Chip label="platform" value={c.platform_tier} />
          {c.role_floor && <Chip label="" value="role-gated" tone="warn" />}
          {c.safety_net && <Chip label="" value="floor option" tone="mute" />}
          {c.source.status === "manual_only" && (
            <Chip label="" value="apply manually" tone="info" />
          )}
        </div>
        <p className="text-sm text-gray-300 mt-2">{c.why}</p>
        {c.adjustment_reason && (
          <p className="text-[11px] text-amber-400/80 mt-2 leading-relaxed">
            Adjusted by judgment: {c.adjustment_reason}
          </p>
        )}
      </div>

      <div className="grid grid-cols-4 gap-2">
        {[
          ["Open roles", c.counts.open],
          ["Eligible", c.counts.eligible],
          ["In Canada", c.counts.canada],
          ["Total tracked", c.counts.total],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded border border-gray-800 py-2 text-center">
            <div className="text-lg text-white tabular-nums">{value as number}</div>
            <div className="text-[10px] text-gray-500">{label as string}</div>
          </div>
        ))}
      </div>

      <Section
        title={`Open roles (${eligible.length + review.length})`}
        subtitle="Ordered by application priority. Click a title for the full posting and scoring detail."
      >
        <div className="space-y-1.5">
          {eligible.map((r) => (
            <RoleRow key={r.job_id} r={r} />
          ))}
          {review.length > 0 && (
            <>
              <p className="text-[11px] text-amber-400 pt-2">
                Needs a human check — usually an ambiguous location
              </p>
              {review.map((r) => (
                <RoleRow key={r.job_id} r={r} />
              ))}
            </>
          )}
          {eligible.length + review.length === 0 && (
            <p className="text-xs text-gray-500">
              Nothing open you could apply to right now.
            </p>
          )}
        </div>
      </Section>

      {blocked.length > 0 && (
        <Section
          title={`Not eligible (${blocked.length})`}
          subtitle="Kept visible so the absence is auditable — mostly roles outside Canada."
        >
          <div className="space-y-1.5 max-h-72 overflow-y-auto">
            {blocked.slice(0, 40).map((r) => (
              <RoleRow key={r.job_id} r={r} />
            ))}
          </div>
        </Section>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <Section title="Source" subtitle="Where these postings come from.">
          <div className="text-xs space-y-1.5">
            <div className="text-gray-400">
              status <span className="text-gray-200">{c.source.status}</span>
              {c.source.connector && (
                <> · connector <span className="text-gray-200">{c.source.connector}</span></>
              )}
            </div>
            {c.source.careers_url && (
              <a
                href={c.source.careers_url}
                target="_blank"
                rel="noreferrer"
                className="text-accent hover:underline break-all block"
              >
                {c.source.careers_url}
              </a>
            )}
            {c.source.note && (
              <p className="text-gray-500 leading-relaxed">{c.source.note}</p>
            )}
          </div>
        </Section>

        <Section
          title="Why this tier"
          subtitle="Nine declared judgments. Argue with a number here rather than with the tier."
        >
          <div className="space-y-2">
            <Metric label="Value — worth once inside" value={c.value} />
            <Metric label="Access — how reachable" value={c.access} />
            <Metric label="Platform — company alone" value={c.platform_score} />
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-3">
            {Object.entries(c.inputs).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2 text-[11px]">
                <span className="inline-flex gap-0.5">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className={`w-1.5 h-1.5 rounded-full ${
                        i < v ? "bg-accent" : "bg-gray-800"
                      }`}
                    />
                  ))}
                </span>
                <span className="text-gray-400" title={INPUT_COPY[k]}>
                  {k}
                </span>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-gray-600 mt-3">
            Assessed {c.assessed_on} · frozen until {c.valid_until}.{" "}
            {c.worth_taking_if_offered
              ? "Worth taking if offered, on the company's merits."
              : "Below the accept threshold — only a strong specific role justifies it."}
          </p>
        </Section>
      </div>
    </div>
  );
}
