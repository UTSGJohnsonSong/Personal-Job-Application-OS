import Link from "next/link";

import { ApiError } from "@/app/components/ApiError";
import { Chip } from "@/app/components/ScoreBits";
import {
  ACTION_COPY,
  POSTURE_COPY,
  RegistryCompany,
  RegistryGroup,
  RegistryList,
  RegistryMeta,
  RegistryView,
  VIEWS,
  registry,
} from "@/lib/registry";

export const dynamic = "force-dynamic";

const TIER_STYLE: Record<string, string> = {
  S: "border-emerald-700 text-emerald-300 bg-emerald-950/40",
  A: "border-blue-700 text-blue-300 bg-blue-950/40",
  B: "border-gray-600 text-gray-300 bg-gray-800/40",
  C: "border-gray-700 text-gray-400",
  D: "border-gray-800 text-gray-500",
};

function isView(v: string | undefined): v is RegistryView {
  return v === "apply" || v === "value" || v === "platform";
}

/** Two bars side by side. The gap between them is the whole point: it says
 *  whether the constraint on a company is reach or worth. */
function Axes({ value, access }: { value: number; access: number }) {
  const bars = [
    { label: "value", v: value, cls: "bg-emerald-500" },
    { label: "access", v: access, cls: "bg-blue-500" },
  ];
  return (
    <div className="space-y-1 w-36 shrink-0">
      {bars.map((b) => (
        <div key={b.label} className="flex items-center gap-2">
          <span className="text-[10px] text-gray-500 w-10">{b.label}</span>
          <div className="h-1.5 bg-gray-800 rounded flex-1 overflow-hidden">
            <div
              className={`h-1.5 ${b.cls}`}
              style={{ width: `${Math.max(0, Math.min(100, b.v))}%` }}
            />
          </div>
          <span className="text-[10px] text-gray-400 w-6 text-right">
            {b.v.toFixed(0)}
          </span>
        </div>
      ))}
    </div>
  );
}

function Row({ c, view }: { c: RegistryCompany; view: RegistryView }) {
  const action = ACTION_COPY[c.action];
  // The value view is the one that can be misread as a second apply queue, so
  // every row there states the action it implies.
  const showAction = view === "value";
  return (
    <div className="rounded border border-gray-800 bg-panel p-3">
      <div className="flex items-start gap-3">
        <span className="text-lg font-semibold text-white w-11 text-right tabular-nums shrink-0">
          {c.score.toFixed(0)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              href={`/registry/${c.key}`}
              className="text-white font-medium hover:underline"
            >
              {c.name}
            </Link>
            {view !== "apply" && (
              <Chip label="apply" value={`${c.priority_tier} ${c.priority_score.toFixed(0)}`} />
            )}
            {view !== "platform" && (
              <Chip label="platform" value={c.platform_tier} />
            )}
            {c.posture !== "balanced" && (
              <Chip
                label=""
                value={POSTURE_COPY[c.posture]}
                tone={c.posture === "worth_forcing" ? "info" : "mute"}
              />
            )}
            {c.safety_net && <Chip label="" value="floor" tone="mute" />}
            {c.role_floor && <Chip label="" value="role-gated" tone="warn" />}
            {c.adjusted && <Chip label="" value="adjusted" tone="warn" />}
            {!c.has_source && <Chip label="" value="no source yet" tone="bad" />}
          </div>
          <p className="text-[11px] text-gray-500 mt-1 line-clamp-2">{c.why}</p>
          {showAction && (
            <p
              className={`text-[11px] mt-1 ${
                action.tone === "warn"
                  ? "text-amber-400"
                  : action.tone === "good"
                    ? "text-emerald-400"
                    : "text-gray-500"
              }`}
            >
              → {action.text}
            </p>
          )}
        </div>
        <Axes value={c.value_score} access={c.access_score} />
      </div>
    </div>
  );
}

function Group({ g, view }: { g: RegistryGroup; view: RegistryView }) {
  return (
    <section>
      <div className="flex items-baseline gap-3 mb-2">
        <span
          className={`text-sm font-semibold px-2 py-0.5 rounded border ${
            TIER_STYLE[g.tier] ?? "border-gray-800 text-gray-500"
          }`}
        >
          {g.tier}
        </span>
        <span className="text-[11px] text-gray-500">{g.count} companies</span>
      </div>
      <div className="grid gap-2">
        {g.companies.map((c) => (
          <Row key={c.key} c={c} view={view} />
        ))}
      </div>
    </section>
  );
}

function Tabs({ active }: { active: RegistryView }) {
  return (
    <div className="flex gap-1 border-b border-gray-800">
      {VIEWS.map((v) => (
        <Link
          key={v.id}
          href={`/registry?view=${v.id}`}
          className={`px-3 py-2 text-sm border-b-2 -mb-px ${
            v.id === active
              ? "border-accent text-white"
              : "border-transparent text-gray-500 hover:text-gray-300"
          }`}
        >
          {v.label}
        </Link>
      ))}
    </div>
  );
}

export default async function RegistryPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string; tier?: string; posture?: string }>;
}) {
  const params = await searchParams;
  const view: RegistryView = isView(params.view) ? params.view : "apply";
  const meta_ = VIEWS.find((v) => v.id === view)!;

  let data: RegistryList | null = null;
  let meta: RegistryMeta | null = null;
  let error: string | null = null;
  try {
    [data, meta] = await Promise.all([
      registry.companies({ view, tier: params.tier, posture: params.posture }),
      registry.meta(),
    ]);
  } catch (e) {
    error = (e as Error).message;
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-white">Company Registry</h1>
        <p className="text-[11px] text-gray-500 mt-1">
          A frozen assessment, not live data. Tier belongs to the company layer and
          never moves because one posting opened or closed.
        </p>
      </div>

      <Tabs active={view} />

      <div className="rounded border border-gray-800 bg-panel px-4 py-3">
        <p className="text-sm text-gray-200">{meta_.question}</p>
        <p className="text-[11px] text-gray-500 mt-1 font-mono">{meta_.formula}</p>
        {view === "value" && (
          <p className="text-[11px] text-amber-400 mt-2">
            This is not a second apply queue. It ignores whether you can get in, so
            several top rows will not answer a cold application — each says which.
          </p>
        )}
        {view === "platform" && (
          <p className="text-[11px] text-gray-500 mt-2">
            Recognition plus a stable co-op programme caps at 88 (an A). Only
            engineering reputation reaches S, and its absence never subtracts.
          </p>
        )}
      </div>

      {error && <ApiError error={error} />}

      {data && meta && (
        <>
          <div className="flex items-center gap-3 text-[11px] text-gray-500">
            <span>{data.total} rated</span>
            {["S", "A", "B", "C", "D"].map((t) => (
              <Link
                key={t}
                href={`/registry?view=${view}${params.tier === t ? "" : `&tier=${t}`}`}
                className={`px-1.5 rounded border ${
                  params.tier === t
                    ? "border-accent text-accent"
                    : "border-gray-800 hover:border-gray-600"
                }`}
              >
                {t} {data.counts[t] ?? 0}
              </Link>
            ))}
            <Link
              href={`/registry?view=${view}&posture=worth_forcing`}
              className="ml-auto text-accent hover:underline"
            >
              Worth forcing →
            </Link>
            <span className="text-gray-700">
              {meta.source_coverage.without_source} of {meta.total_rated} have no
              source yet
            </span>
          </div>

          {data.groups.map((g) => (
            <Group key={g.tier} g={g} view={view} />
          ))}
        </>
      )}
    </div>
  );
}
