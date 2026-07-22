import { api, JobItem } from "@/lib/api";

function priorityLabel(p: number): string {
  return p === 1 ? "First-party ATS" : p === 2 ? "Gov/University" : "Aggregator";
}

function JobCard({ job }: { job: JobItem }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-panel p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-white font-medium">{job.title}</div>
          <div className="text-xs text-gray-400 mt-1">
            {job.remote_mode ?? "—"} · {priorityLabel(job.source_priority)} ·{" "}
            <span className="capitalize">{job.current_status}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-gray-500">freshness</div>
          <div className="text-sm text-gray-200">{(job.freshness_score * 100).toFixed(0)}%</div>
        </div>
      </div>
      {job.canonical_application_url && (
        <a
          href={job.canonical_application_url}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-accent hover:underline mt-2 inline-block"
        >
          Official application link ↗
        </a>
      )}
    </div>
  );
}

export default async function InboxPage() {
  let items: JobItem[] = [];
  let error: string | null = null;
  try {
    const res = await api.jobs();
    items = res.items;
  } catch (e) {
    error = (e as Error).message;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-white">Job Inbox</h1>
      {error && (
        <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-4 text-amber-200 text-sm">
          Could not reach the API ({error}).
        </div>
      )}
      {!error && items.length === 0 && (
        <div className="text-sm text-gray-400">
          No jobs yet. Run the seed: <code>python -m app.seed.seed_data</code>.
        </div>
      )}
      <div className="grid gap-3">
        {items.map((j) => (
          <JobCard key={j.id} job={j} />
        ))}
      </div>
    </div>
  );
}
