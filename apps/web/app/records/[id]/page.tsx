import Link from "next/link";

import { changeStatus } from "@/app/actions";
import { api, ApplicationRecord, RecordAnswer } from "@/lib/api";

export const dynamic = "force-dynamic";

// Statuses the user can flip manually. `submitted` is deliberately absent —
// it is only reachable through the per-job confirmation flow.
const STATUSES = [
  "saved", "preparing", "ready_for_review", "application_started",
  "confirmation_received", "recruiter_contact", "assessment", "phone_screen",
  "interview", "final_interview", "offer", "accepted", "rejected",
  "withdrawn", "position_closed",
];

function AnswerCard({ a }: { a: RecordAnswer }) {
  const border = a.needs_user_input
    ? "border-amber-800"
    : a.provenance === "generated_draft"
      ? "border-blue-900"
      : "border-gray-800";
  return (
    <div className={`rounded border ${border} bg-black/20 p-3`}>
      <div className="text-xs text-gray-400">{a.question}</div>
      <div className="text-sm text-gray-100 mt-1 whitespace-pre-wrap">
        {a.answer ?? <span className="text-amber-400">(blank — you need to answer this)</span>}
      </div>
      <div className="flex gap-2 mt-2 flex-wrap">
        {a.is_sensitive && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-950 text-red-300 border border-red-900">
            Sensitive
          </span>
        )}
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">
          source: {a.provenance}
        </span>
        {a.answer_source && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">
            from {a.answer_source}
          </span>
        )}
        {!a.user_confirmed && a.answer && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-900">
            draft · unconfirmed
          </span>
        )}
      </div>
    </div>
  );
}

export default async function RecordDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let rec: ApplicationRecord | null = null;
  let error: string | null = null;
  try {
    rec = await api.record(id);
  } catch (e) {
    error = (e as Error).message;
  }

  if (error || !rec) {
    return (
      <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-4 text-amber-200 text-sm">
        Could not load this record ({error})
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href="/records" className="text-xs text-gray-500 hover:text-white">
          ← Applications
        </Link>
        <h1 className="text-lg font-semibold text-white mt-2">{rec.job.title}</h1>
        <div className="flex items-center gap-3 mt-2 flex-wrap">
          <span className="text-xs px-2 py-0.5 rounded border border-gray-700 bg-gray-800 text-gray-300">
            {rec.status}
          </span>
          {rec.resume_version && (
            <span className="text-xs text-gray-400">
              Resume version: <span className="text-white">{rec.resume_version.name}</span>
              {rec.resume_version.direction && `(${rec.resume_version.direction})`}
            </span>
          )}
          {rec.job.apply_url && (
            <a
              href={rec.job.apply_url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-accent hover:underline"
            >
              Official link ↗
            </a>
          )}
        </div>
      </div>

      {/* manual status switch */}
      <section>
        <h2 className="text-sm font-semibold text-white mb-2">Update status</h2>
        <form action={changeStatus} className="flex gap-2 items-center">
          <input type="hidden" name="application_id" value={rec.application_id} />
          <select
            name="status"
            defaultValue={rec.status}
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button className="text-sm px-3 py-1 rounded bg-accent text-white hover:opacity-90">
            Save
          </button>
          <span className="text-xs text-gray-600">
            (submitted is not here — a real submission requires per-job confirmation)
          </span>
        </form>
      </section>

      {(rec.uncertainties.length > 0 || rec.risks.length > 0) && (
        <section className="rounded-lg border border-amber-900 bg-amber-950/30 p-4">
          <h2 className="text-sm font-semibold text-amber-200 mb-2">Needs attention</h2>
          {rec.risks.map((r) => (
            <div key={r} className="text-xs text-red-300">⚠ {r}</div>
          ))}
          {rec.uncertainties.map((u) => (
            <div key={u} className="text-xs text-amber-300">? {u}</div>
          ))}
        </section>
      )}

      <section>
        <h2 className="text-sm font-semibold text-white mb-2">
          Application answers ({rec.answers.length})
        </h2>
        {rec.answers.length === 0 ? (
          <p className="text-sm text-gray-500">No answers recorded yet.</p>
        ) : (
          <div className="grid gap-2">
            {rec.answers.map((a, i) => (
              <AnswerCard key={`${a.question}-${i}`} a={a} />
            ))}
          </div>
        )}
      </section>

      {rec.cover_letter && (
        <section>
          <h2 className="text-sm font-semibold text-white mb-2">Cover Letter</h2>
          <pre className="rounded border border-gray-800 bg-black/20 p-3 text-sm text-gray-200 whitespace-pre-wrap font-sans">
            {rec.cover_letter}
          </pre>
        </section>
      )}

      <section>
        <h2 className="text-sm font-semibold text-white mb-2">Timeline</h2>
        <div className="space-y-1">
          {rec.timeline.length === 0 && (
            <p className="text-sm text-gray-500">No events yet.</p>
          )}
          {rec.timeline.map((e, i) => (
            <div key={i} className="text-xs text-gray-400 flex gap-3">
              <span className="text-gray-600 w-40">
                {new Date(e.at).toLocaleString()}
              </span>
              <span>
                {e.event}
                {e.from && e.to && ` · ${e.from} → ${e.to}`}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
