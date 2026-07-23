import Link from "next/link";

import { ApiError } from "@/app/components/ApiError";
import { Chip, Metric, Section, eligibilityTone } from "@/app/components/ScoreBits";
import { CompanyDetail, DetailRole, inbox } from "@/lib/inbox";

export const dynamic = "force-dynamic";

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${(v * 100).toFixed(0)}%`;
}

/** Full score row — never a single "match" number. */
function RoleRow({ r, rank }: { r: DetailRole; rank?: number | null }) {
  return (
    <div className="rounded border border-gray-800 bg-black/20 p-3">
      <div className="flex items-start gap-3">
        {rank != null && (
          <div className="text-gray-500 text-xs w-5 pt-0.5">#{rank}</div>
        )}
        <div className="flex-1 min-w-0">
          <div className="text-sm text-white">{r.title}</div>
          <div className="flex gap-1.5 flex-wrap mt-1.5">
            <Chip label="Eligibility" value={r.eligibility} tone={eligibilityTone(r.eligibility)} />
            <Chip label="Role" value={`${r.role_band} · ${r.role_family}`} />
            {r.similarity_group && <Chip label="Group" value={r.similarity_group} />}
            {r.location && <Chip label="" value={r.location} />}
            {!r.is_official && <Chip label="" value="no official link" tone="warn" />}
            {r.duplicates_applied_role && (
              <Chip label="" value="duplicates an applied role" tone="warn" />
            )}
          </div>
          {r.reason && (
            <p className="text-[11px] text-emerald-400 mt-2">✓ {r.reason}</p>
          )}
          {r.superseded_by && (
            <p className="text-[11px] text-amber-400 mt-1">
              superseded by “{r.superseded_by}”
            </p>
          )}
          {r.redundancy_risk != null && r.redundancy_risk > 0 && (
            <p className="text-[11px] text-gray-500 mt-1">
              redundancy risk {(r.redundancy_risk * 100).toFixed(0)}%
            </p>
          )}
        </div>
        <div className="text-right shrink-0">
          <div className="text-xl font-semibold text-white">
            {r.application_priority.toFixed(0)}
          </div>
          <div className="text-[10px] text-gray-500">Priority /100</div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mt-3">
        <Metric label="Platform" value={r.company_platform_value} />
        <Metric label="Role Strategic" value={r.role_strategic_value} />
        <Metric label="Current Fit" value={r.current_fit} />
        <Metric label="Team" value={r.team_quality} />
        <Metric label="Optionality" value={r.career_optionality} />
      </div>

      <div className="flex gap-3 mt-2 text-[11px]">
        <span className="text-gray-600">Evidence {pct(r.evidence_coverage)}</span>
        {r.apply_url && (
          <a href={r.apply_url} target="_blank" rel="noreferrer"
             className="text-accent hover:underline">
            Official application ↗
          </a>
        )}
        <Link href={`/priority?compare=${r.job_id}`} className="text-gray-400 hover:text-white">
          Compare
        </Link>
      </div>
    </div>
  );
}

export default async function CompanyDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let d: CompanyDetail | null = null;
  let error: string | null = null;
  try {
    d = await inbox.company(id);
  } catch (e) {
    error = (e as Error).message;
  }
  if (error || !d) return <ApiError error={error ?? "unknown error"} />;

  const o = d.overview;
  const set = d.recommended_application_set;

  return (
    <div className="space-y-5">
      <div>
        <Link href="/companies" className="text-xs text-gray-500 hover:text-white">
          ← Companies by Tier
        </Link>
        <h1 className="text-lg font-semibold text-white mt-2">{o.name}</h1>
        <div className="flex gap-1.5 flex-wrap mt-2">
          <Chip label="Tier" value={o.tier_display} />
          <Chip label="Platform" value={o.platform_value.toFixed(0)} />
          <Chip label="Evidence" value={pct(o.evidence_coverage)}
                tone={o.evidence_coverage < 0.65 ? "warn" : "mute"} />
          <Chip label="Official src" value={pct(o.official_source_coverage)} />
          {o.provisional && <Chip label="" value="Provisional" tone="warn" />}
        </div>
      </div>

      <Section title="Overview">
        <div className="grid grid-cols-3 md:grid-cols-6 gap-2 text-center">
          {[
            ["Open roles", o.total_open_roles],
            ["Canada", o.canada_roles],
            ["GTA", o.gta_roles],
            ["Student", o.student_roles],
            ["Relevant", o.relevant_roles],
            ["Submitted", o.submitted_applications],
          ].map(([l, v]) => (
            <div key={String(l)} className="rounded border border-gray-800 py-2">
              <div className="text-lg text-white">{v as number}</div>
              <div className="text-[10px] text-gray-500">{l as string}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section
        title={`Recommended Application Set — ${set.recommended.length} of ${set.limit}`}
        subtitle="A small set of genuinely distinct roles, not every requisition. Every inclusion and exclusion states its reason."
      >
        {set.notes.map((n) => (
          <p key={n} className="text-[11px] text-amber-300 mb-2">⚠ {n}</p>
        ))}
        <div className="grid gap-2">
          {set.recommended.map((r) => (
            <RoleRow key={r.job_id} r={r} rank={r.company_internal_rank} />
          ))}
          {set.recommended.length === 0 && (
            <p className="text-sm text-gray-500">Nothing recommended right now.</p>
          )}
        </div>

        {set.excluded.length > 0 && (
          <div className="mt-4">
            <h3 className="text-xs font-semibold text-gray-400 mb-2">
              Held back ({set.excluded.length})
            </h3>
            <div className="grid gap-2">
              {set.excluded.map((r) => (
                <RoleRow key={r.job_id} r={r} />
              ))}
            </div>
          </div>
        )}
      </Section>

      <Section title="Top Recommended Roles">
        <div className="grid gap-2">
          {d.top_recommended_roles.map((r, i) => (
            <RoleRow key={r.job_id} r={r} rank={i + 1} />
          ))}
        </div>
      </Section>

      {d.student_early_careers.length > 0 && (
        <Section title={`Student / Early Careers (${d.student_early_careers.length})`}>
          <div className="grid gap-2">
            {d.student_early_careers.map((r) => (
              <RoleRow key={r.job_id} r={r} />
            ))}
          </div>
        </Section>
      )}

      <Section title={`All Relevant Roles (${d.all_relevant_roles.length})`}>
        <div className="grid gap-2">
          {d.all_relevant_roles.map((r, i) => (
            <RoleRow key={r.job_id} r={r} rank={i + 1} />
          ))}
        </div>
      </Section>

      {d.applied_roles.length > 0 && (
        <Section title={`Applied Roles (${d.applied_roles.length})`}>
          <div className="grid gap-2">
            {d.applied_roles.map((r) => (
              <RoleRow key={r.job_id} r={r} />
            ))}
          </div>
        </Section>
      )}

      <Section
        title="Official Sources"
        subtitle="Roles must come from the employer's own careers page or ATS. A third-party link is discovery only and can never be submitted automatically."
      >
        <p className="text-xs text-gray-300">
          {d.official_sources.roles_with_official_link} role(s) have an official
          application link.
        </p>
        {d.official_sources.roles_third_party_only.length > 0 && (
          <div className="mt-2 grid gap-2">
            <p className="text-[11px] text-amber-400">
              {d.official_sources.roles_third_party_only.length} role(s) have no official
              link yet — resolve before applying:
            </p>
            {d.official_sources.roles_third_party_only.map((r) => (
              <RoleRow key={r.job_id} r={r} />
            ))}
          </div>
        )}
      </Section>

      <p className="text-[10px] text-gray-600">
        calculation {d.calculation.calculation_version} · ranking formula{" "}
        {d.calculation.ranking_formula_version}
      </p>
    </div>
  );
}
