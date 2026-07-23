import Link from "next/link";

import { ApiError } from "@/app/components/ApiError";
import { Chip, Metric, Section } from "@/app/components/ScoreBits";
import { POSTURE_COPY, RegistryDetail, SOURCE_COPY, registry } from "@/lib/registry";

export const dynamic = "force-dynamic";

const INPUT_COPY: Record<string, string> = {
  brand_ca: "Recognition in Canada (weighted 0.60)",
  brand_us: "Recognition in the US (0.25)",
  brand_cn: "Recognition in China (0.15)",
  tech: "Engineering reputation among engineers",
  depth: "Size of the real Canadian technology organisation",
  role: "Availability of analyst / product / DS roles you could win",
  domain: "Fit with health, fintech or applied ToB AI",
  founder: "Customer contact, sales visibility, cofounder pool, equity",
  program: "Maturity of the published co-op programme",
};

const VALUE_KEYS = ["brand_ca", "brand_us", "brand_cn", "tech", "domain", "founder"];

function Dots({ n }: { n: number }) {
  return (
    <span className="inline-flex gap-0.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={`w-2 h-2 rounded-full ${i < n ? "bg-accent" : "bg-gray-800"}`}
        />
      ))}
    </span>
  );
}

function Terms({ terms, total }: { terms: Record<string, number>; total: string }) {
  return (
    <div className="space-y-1">
      {Object.entries(terms).map(([k, v]) => (
        <div key={k} className="flex justify-between text-xs">
          <span className="text-gray-400">{k}</span>
          <span className="text-gray-200 tabular-nums">{v.toFixed(1)}</span>
        </div>
      ))}
      <div className="flex justify-between text-xs border-t border-gray-800 pt-1 mt-1">
        <span className="text-gray-300">total</span>
        <span className="text-white font-medium tabular-nums">{total}</span>
      </div>
    </div>
  );
}

export default async function CompanyRegistryPage({
  params,
}: {
  params: Promise<{ key: string }>;
}) {
  const { key } = await params;
  let c: RegistryDetail | null = null;
  let error: string | null = null;
  try {
    c = await registry.company(key);
  } catch (e) {
    error = (e as Error).message;
  }

  if (error || !c) {
    return (
      <div className="space-y-4">
        <Link href="/registry" className="text-xs text-accent hover:underline">
          ← Registry
        </Link>
        <ApiError error={error ?? "not found"} />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <Link href="/registry" className="text-xs text-accent hover:underline">
        ← Registry
      </Link>

      <div>
        <h1 className="text-lg font-semibold text-white">{c.name}</h1>
        <div className="flex gap-1.5 flex-wrap mt-2">
          <Chip label="apply" value={`${c.priority_tier} · ${c.priority_score.toFixed(0)}`} />
          <Chip label="value" value={`${c.value_tier} · ${c.value_score.toFixed(0)}`} />
          <Chip label="platform" value={`${c.platform_tier} · ${c.platform_score.toFixed(0)}`} />
          <Chip label="" value={POSTURE_COPY[c.posture]} tone={
            c.posture === "worth_forcing" ? "info" : "mute"
          } />
          {c.role_floor && <Chip label="" value="role-gated" tone="warn" />}
          <Chip
            label=""
            value={SOURCE_COPY[c.source.status].text}
            tone={SOURCE_COPY[c.source.status].tone as "good" | "warn" | "info" | "bad"}
          />
        </div>
        <p className="text-sm text-gray-300 mt-3">{c.why}</p>
      </div>

      <Section
        title="Official source"
        subtitle="Where postings actually come from. A company we cannot reach automatically stays in the system and goes to the manual queue — connector coverage never decides which employers exist."
      >
        <div className="text-xs space-y-1.5">
          {c.source.careers_url && (
            <a
              href={c.source.careers_url}
              target="_blank"
              rel="noreferrer"
              className="text-accent hover:underline break-all"
            >
              {c.source.careers_url}
            </a>
          )}
          {c.source.connector && (
            <div className="text-gray-400">
              connector: <span className="text-gray-200">{c.source.connector}</span>
            </div>
          )}
          {c.source.observed_jobs != null && (
            <div className="text-gray-400">
              observed {c.source.probed_on}:{" "}
              <span className="text-gray-200">{c.source.observed_jobs}</span> postings ·{" "}
              <span className="text-gray-200">{c.source.observed_canada}</span> Canadian ·{" "}
              <span className="text-gray-200">
                {c.source.observed_student_canada}
              </span>{" "}
              Canadian student
            </div>
          )}
          {c.source.note && (
            <p className="text-gray-500 leading-relaxed">{c.source.note}</p>
          )}
        </div>
      </Section>

      <div className="grid md:grid-cols-2 gap-4">
        <Section
          title="Value"
          subtitle="What the experience is worth once you are inside. This is the number for an offer decision — access has already resolved by then."
        >
          <Terms terms={c.breakdown.value_terms} total={c.value_score.toFixed(1)} />
          <p className="text-[11px] text-gray-500 mt-3">
            {c.worth_taking_if_offered
              ? "Above the accept threshold: worth taking on the company's merits."
              : "Below the accept threshold: only a genuinely good specific role justifies it."}
          </p>
        </Section>

        <Section
          title="Access"
          subtitle="How reachable it actually is. Every term here is a probability, which is why none of them belong in the offer decision."
        >
          <Terms terms={c.breakdown.access_terms} total={c.access_score.toFixed(1)} />
          <p className="text-[11px] text-gray-500 mt-3">
            Application priority = √(value × access) ={" "}
            <span className="text-gray-300">{c.priority_score.toFixed(1)}</span>. Geometric,
            so one axis near zero cannot be averaged away by the other.
          </p>
        </Section>
      </div>

      <Section
        title="Platform"
        subtitle="The company on its own terms, independent of you. Recognition plus a stable programme caps at 88; only engineering reputation reaches S."
      >
        <div className="grid md:grid-cols-2 gap-4">
          <Terms terms={c.breakdown.platform_terms} total={c.platform_score.toFixed(1)} />
          <div className="space-y-2">
            <Metric label="Value" value={c.value_score} />
            <Metric label="Access" value={c.access_score} />
            <Metric label="Apply priority" value={c.priority_score} />
          </div>
        </div>
      </Section>

      <Section
        title="Inputs"
        subtitle="Every score above comes from these nine judgments. They are declared assessments, not verified facts — argue with a number here rather than with a tier."
      >
        <div className="grid md:grid-cols-2 gap-x-6 gap-y-2">
          {Object.entries(c.inputs).map(([k, v]) => (
            <div key={k} className="flex items-center gap-3 text-xs">
              <Dots n={v} />
              <span className="text-gray-300 w-20">{k}</span>
              <span className="text-gray-600 text-[11px] flex-1">{INPUT_COPY[k]}</span>
              <span className={VALUE_KEYS.includes(k) ? "text-emerald-500" : "text-blue-500"}>
                {VALUE_KEYS.includes(k) ? "value" : "access"}
              </span>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-gray-600 mt-3">
          Sensitivity: depth or role ±1 moves access by 13.3; tech or domain ±1 moves
          value by 8.3. Tier bands are 8–10 wide, so a single input being off by one
          can move a tier.
        </p>
      </Section>

      {c.adjusted && (
        <Section
          title="Adjusted by judgment"
          subtitle="The algorithm landed somewhere I disagreed with. Both passes are kept so they can be compared."
        >
          <div className="text-xs space-y-1">
            <div className="text-gray-400">
              algorithm: apply {c.breakdown.algo_priority_tier} · platform{" "}
              {c.breakdown.algo_platform_tier}
            </div>
            <div className="text-gray-200">
              final: apply {c.priority_tier} · platform {c.platform_tier}
            </div>
            {c.override_reason && (
              <p className="text-gray-400 mt-2 leading-relaxed">{c.override_reason}</p>
            )}
          </div>
        </Section>
      )}

      <p className="text-[10px] text-gray-700">
        Assessed {c.assessed_on} · frozen until {c.valid_until} · re-run on a
        structural event (Canadian office opened or closed, programme changed,
        acquisition, layoffs)
      </p>
    </div>
  );
}
