export const dynamic = "force-dynamic";

/**
 * Shown when APP_PASSWORD / APP_SECRET_KEY are not configured. The app fails
 * CLOSED: with no password it refuses to render data rather than exposing it.
 */
export default function SetupRequired() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="max-w-md rounded-lg border border-amber-800 bg-amber-950/40 p-6 text-amber-200 text-sm space-y-3">
        <h1 className="font-semibold">Setup required — login is not configured</h1>
        <p className="text-amber-300/80 text-xs">
          This deployment is refusing to serve data because no password is set.
          Configure both environment variables and redeploy:
        </p>
        <pre className="text-[11px] bg-black/30 rounded p-3 text-amber-100 overflow-x-auto">
{`APP_PASSWORD    = <a long password you choose>
APP_SECRET_KEY  = <32+ random chars, used to sign sessions>`}
        </pre>
        <p className="text-amber-300/60 text-[11px]">
          Failing closed is intentional: an unconfigured instance must never fall
          back to serving personal data publicly.
        </p>
      </div>
    </div>
  );
}
