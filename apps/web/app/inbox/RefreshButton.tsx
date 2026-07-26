"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { RefreshStatus } from "@/lib/pool";

function mmss(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function RefreshButton({
  estimatedSeconds,
  sources,
  lastRefreshed,
}: {
  estimatedSeconds: number;
  sources: number;
  lastRefreshed: string | null;
}) {
  const router = useRouter();
  const [status, setStatus] = useState<RefreshStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const poll = useCallback(async () => {
    const res = await fetch("/api/refresh", { cache: "no-store" });
    const next: RefreshStatus = await res.json();
    setStatus(next);
    if (!next.running) {
      stop();
      setStarting(false);
      // Pull the freshly synced pool rather than leaving stale numbers on screen.
      router.refresh();
    }
  }, [router, stop]);

  useEffect(() => stop, [stop]);

  async function start() {
    setStarting(true);
    await fetch("/api/refresh", { method: "POST" });
    await poll();
    stop();
    timer.current = setInterval(poll, 1000);
  }

  const running = status?.running || starting;
  const percent = status?.percent ?? 0;

  return (
    <div className="rounded-lg border border-gray-800 bg-panel p-3 min-w-[19rem]">
      <div className="flex items-center gap-3">
        <button
          onClick={start}
          disabled={running}
          className={`text-xs px-3 py-1.5 rounded border ${
            running
              ? "border-gray-800 text-gray-600 cursor-not-allowed"
              : "border-gray-700 text-gray-200 hover:border-accent hover:text-accent"
          }`}
        >
          {running ? "Refreshing…" : "Refresh roles"}
        </button>
        <div className="text-[11px] text-gray-500 leading-tight">
          {running ? (
            <>
              {status?.stage === "sources"
                ? `${status.done}/${status.total} sources`
                : status?.stage === "scoring"
                  ? "recomputing priorities"
                  : status?.stage === "rebuilding"
                    ? "rebuilding recommendations"
                    : "starting"}
              {status?.current ? ` · ${status.current}` : ""}
            </>
          ) : (
            <>
              {sources} sources · about {mmss(estimatedSeconds)}
              {lastRefreshed && (
                <div className="text-gray-600">
                  last {new Date(lastRefreshed).toLocaleString()}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {running && (
        <div className="mt-2">
          <div className="h-1.5 bg-gray-800 rounded overflow-hidden">
            <div
              className="h-1.5 bg-accent transition-all duration-500"
              style={{ width: `${percent}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-gray-500 mt-1">
            <span>{percent}%</span>
            <span>
              {mmss(status?.elapsed_seconds ?? 0)} elapsed
              {status?.eta_seconds ? ` · ~${mmss(status.eta_seconds)} left` : ""}
            </span>
          </div>
        </div>
      )}

      {/* Success and failure are mutually exclusive. They used to be two
          sibling blocks, so a run that failed showed a green "Done · 0 new
          roles" directly above the red reason — and green reads first. */}
      {status && !status.running && status.finished_at && !status.error && (
        <p className="text-[11px] text-emerald-400 mt-2">
          Done · {status.new_jobs} new role{status.new_jobs === 1 ? "" : "s"}
        </p>
      )}
      {status?.error && (
        <p className="text-[11px] text-red-400 mt-2">{status.error}</p>
      )}
      {/* Kept after the run, not only during it. The per-source lines are the
          only place a single failing board is ever named, and clearing them on
          completion threw away the evidence at the moment it became useful. */}
      {status?.log && status.log.length > 0 && (
        <ul className="mt-2 space-y-0.5 max-h-32 overflow-y-auto">
          {status.log.slice(running ? -5 : -12).map((line, i) => (
            <li key={i} className="text-[10px] text-gray-600 truncate" title={line}>
              {line}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
