/**
 * Renders an actionable message for API failures.
 * A 401 means the token is missing/wrong — NOT that the backend is down, so it
 * must not tell the user to start uvicorn.
 */
export function ApiError({ error }: { error: string }) {
  const unauthorized = error.includes("401");
  const notFound = error.includes("404");
  const unavailable = error.includes("503");

  return (
    <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-4 text-amber-200 text-sm space-y-2">
      {unauthorized && (
        <>
          <div className="font-medium">Unauthorized (401) — API token missing or wrong.</div>
          <div className="text-amber-300/80 text-xs">
            The backend is reachable but rejected this request. Set{" "}
            <code className="text-amber-100">API_TOKEN</code> in the web app&apos;s
            environment variables (no <code>NEXT_PUBLIC_</code> prefix) to the same
            value configured on the API, then redeploy.
          </div>
        </>
      )}
      {unavailable && (
        <>
          <div className="font-medium">API refusing to serve (503).</div>
          <div className="text-amber-300/80 text-xs">
            The API has no <code className="text-amber-100">API_TOKEN</code> configured
            and is refusing to serve protected data rather than exposing it.
          </div>
        </>
      )}
      {notFound && <div className="font-medium">Not found (404).</div>}
      {!unauthorized && !unavailable && !notFound && (
        <>
          <div className="font-medium">Could not reach the API.</div>
          <div className="text-amber-300/80 text-xs">
            Check <code className="text-amber-100">NEXT_PUBLIC_API_BASE</code>. For local
            development run <code>uvicorn app.main:app --reload</code> in{" "}
            <code>apps/api</code>. A hosted free-tier API may also be waking from
            sleep — retry in ~50s.
          </div>
        </>
      )}
      <div className="text-amber-300/50 text-[11px]">{error}</div>
    </div>
  );
}
