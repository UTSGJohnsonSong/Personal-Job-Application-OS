"use client";

import Link from "next/link";
import { useState } from "react";

import { PoolCompany, PoolGroup, TIER_STYLE, eligibilityTone } from "@/lib/pool";

function RoleLine({ r }: { r: PoolCompany["top_roles"][number] }) {
  return (
    <div className="flex items-baseline gap-2 text-xs py-0.5">
      <span className="w-4 text-right text-gray-600 tabular-nums">{r.rank}</span>
      <Link
        href={`/rankings/${r.job_id}`}
        className="text-gray-200 hover:text-accent hover:underline truncate flex-1"
      >
        {r.title}
      </Link>
      {r.location && (
        <span
          className={`text-[10px] shrink-0 ${
            r.in_canada ? "text-emerald-500" : "text-gray-600"
          }`}
        >
          {r.location.length > 24 ? `${r.location.slice(0, 24)}…` : r.location}
        </span>
      )}
      <span className={`text-[10px] shrink-0 ${eligibilityTone(r.eligibility)}`}>
        {r.eligibility}
      </span>
      <span className="w-7 text-right text-gray-300 tabular-nums shrink-0">
        {r.priority == null ? "—" : r.priority.toFixed(0)}
      </span>
    </div>
  );
}

function CompanyCard({ c }: { c: PoolCompany }) {
  const dim = c.open_roles === 0;
  return (
    <div
      className={`rounded-lg border p-3 ${
        dim ? "border-gray-900 bg-panel/40" : "border-gray-800 bg-panel"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            href={`/pool/${c.key}`}
            className={`font-medium hover:underline ${
              dim ? "text-gray-400" : "text-white"
            }`}
          >
            {c.name}
          </Link>
          <div className="flex gap-2 items-center flex-wrap mt-1 text-[10px] text-gray-500">
            <span>platform {c.platform_tier}</span>
            <span>value {c.value.toFixed(0)}</span>
            <span>access {c.access.toFixed(0)}</span>
            {c.canada_roles > 0 && (
              <span className="text-emerald-500">{c.canada_roles} in Canada</span>
            )}
            {c.safety_net && <span className="text-gray-600">floor</span>}
            {c.source_status === "manual_only" && (
              <span className="text-blue-400">apply manually</span>
            )}
            {c.source_status === "searching" && (
              <span className="text-gray-600">no source yet</span>
            )}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-xl font-semibold text-white tabular-nums">
            {c.score.toFixed(0)}
          </div>
          <div className="text-[10px] text-gray-600">
            {c.open_roles} open
          </div>
        </div>
      </div>

      {c.top_roles.length > 0 ? (
        <div className="mt-2 pt-2 border-t border-gray-800/60">
          {c.top_roles.map((r) => (
            <RoleLine key={r.job_id} r={r} />
          ))}
          {c.has_more && (
            <Link
              href={`/pool/${c.key}`}
              className="inline-block mt-1 text-[11px] text-accent hover:underline"
            >
              Expand — all {c.open_roles} roles and full company detail →
            </Link>
          )}
        </div>
      ) : (
        <p className="mt-2 pt-2 border-t border-gray-800/60 text-[11px] text-gray-600">
          {c.source_status === "manual_only"
            ? "No feed for this employer — open its careers page to apply."
            : c.source_status === "searching"
              ? "No source mapped yet, so no roles are being tracked."
              : "No open roles right now."}
          <Link href={`/pool/${c.key}`} className="text-accent hover:underline ml-1">
            Company detail →
          </Link>
        </p>
      )}
    </div>
  );
}

export function TierSection({
  group,
  defaultOpen,
}: {
  group: PoolGroup;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  // Companies with nothing open are hidden until asked for: they are the bulk
  // of every tier and would otherwise bury the ones you can act on.
  const [showEmpty, setShowEmpty] = useState(false);
  const live = group.companies.filter((c) => c.open_roles > 0);
  const empty = group.companies.filter((c) => c.open_roles === 0);
  const visible = showEmpty ? [...live, ...empty] : live;

  return (
    <section>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-3 w-full text-left py-1 group"
      >
        <span className="text-gray-600 text-xs w-3">{open ? "▾" : "▸"}</span>
        <span
          className={`text-sm font-semibold px-2 py-0.5 rounded border ${
            TIER_STYLE[group.tier] ?? "border-gray-800 text-gray-500"
          }`}
        >
          {group.tier}
        </span>
        <span className="text-[11px] text-gray-500 group-hover:text-gray-400">
          {group.company_count} companies · {group.open_roles} open roles ·{" "}
          {live.length} hiring now
        </span>
      </button>

      {open && (
        <div className="pl-6 mt-2 space-y-2">
          {visible.length === 0 && (
            <p className="text-[11px] text-gray-600">
              No company in this tier has open roles right now.
            </p>
          )}
          {visible.map((c) => (
            <CompanyCard key={c.key} c={c} />
          ))}
          {empty.length > 0 && (
            <button
              onClick={() => setShowEmpty((v) => !v)}
              className="text-[11px] text-gray-600 hover:text-gray-400"
            >
              {showEmpty
                ? `Hide ${empty.length} with nothing open`
                : `Show ${empty.length} with nothing open`}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
