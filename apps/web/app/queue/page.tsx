import Link from "next/link";

import { queueRemove } from "@/app/actions";
import { api, QueueItem } from "@/lib/api";

export const dynamic = "force-dynamic";

function Badge({ text, tone }: { text: string; tone: "good" | "warn" | "bad" | "mute" }) {
  const tones = {
    good: "bg-emerald-950 text-emerald-300 border-emerald-800",
    warn: "bg-amber-950 text-amber-300 border-amber-800",
    bad: "bg-red-950 text-red-300 border-red-800",
    mute: "bg-gray-800 text-gray-300 border-gray-700",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${tones[tone]}`}>{text}</span>
  );
}

function eligTone(v: string | null): "good" | "warn" | "bad" | "mute" {
  if (v === "eligible") return "good";
  if (v === "likely_eligible") return "good";
  if (v === "uncertain") return "warn";
  if (v === "ineligible" || v === "likely_ineligible") return "bad";
  return "mute";
}

function Row({ item, index }: { item: QueueItem; index: number }) {
  const stale = item.source_status !== "open" && item.source_status !== "updated";
  return (
    <div className="rounded-lg border border-gray-800 bg-panel p-4">
      <div className="flex items-start gap-3">
        <div className="text-gray-500 text-sm w-6 pt-0.5">{index + 1}</div>
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-white font-medium">{item.title}</span>
            {item.score !== null && (
              <Badge text={`score ${item.score.toFixed(2)}`} tone="mute" />
            )}
            {item.strategy && <Badge text={item.strategy} tone="mute" />}
            {item.eligibility && (
              <Badge text={item.eligibility} tone={eligTone(item.eligibility)} />
            )}
            {item.needs_confirmation && <Badge text="Needs your confirmation" tone="warn" />}
            {stale && <Badge text="Source closed" tone="bad" />}
          </div>

          {item.queue_note && (
            <div className="text-xs text-gray-400 mt-1">Note: {item.queue_note}</div>
          )}

          {item.why.length > 0 && (
            <div className="text-xs text-emerald-400 mt-2">
              ✓ {item.why.slice(0, 2).join(" · ")}
            </div>
          )}
          {item.why_not.length > 0 && (
            <div className="text-xs text-amber-400 mt-1">
              ! {item.why_not.slice(0, 2).join(" · ")}
            </div>
          )}
          {item.unknowns.length > 0 && (
            <div className="text-xs text-gray-500 mt-1">
              ? Unknown: {item.unknowns.join(" · ")}
            </div>
          )}

          <div className="flex items-center gap-3 mt-3">
            {item.apply_url && (
              <a
                href={item.apply_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-accent hover:underline"
              >
                Official application link ↗
              </a>
            )}
            <Link
              href={`/records/${item.application_id}`}
              className="text-xs text-gray-400 hover:text-white"
            >
              Application record →
            </Link>
            {item.suggested_minutes !== null && (
              <span className="text-xs text-gray-600">
                Suggested {item.suggested_minutes}  min
              </span>
            )}
            <form action={queueRemove} className="ml-auto">
              <input type="hidden" name="job_id" value={item.job_id} />
              <button className="text-xs text-gray-500 hover:text-red-400">Remove</button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

export default async function QueuePage() {
  let items: QueueItem[] = [];
  let error: string | null = null;
  try {
    items = (await api.queue()).items;
  } catch (e) {
    error = (e as Error).message;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-white">Apply Queue</h1>
        <p className="text-xs text-gray-500 mt-1">
          Ordered by value (manual priority → priority score → freshness). At apply time, work top-down.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-4 text-amber-200 text-sm">
          Could not load the queue ({error})
        </div>
      )}

      {!error && items.length === 0 && (
        <div className="text-sm text-gray-400">
          Queue is empty. Go to <Link href="/inbox" className="text-accent hover:underline">Job Inbox</Link>{" "}
          and add the jobs you want to apply to.
        </div>
      )}

      <div className="grid gap-3">
        {items.map((it, i) => (
          <Row key={it.application_id} item={it} index={i} />
        ))}
      </div>
    </div>
  );
}
