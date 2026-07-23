/**
 * Build provenance. Shown on every page so it is always possible to tell which
 * commit and ranking formula produced what is on screen.
 */
export function VersionFooter() {
  const commit =
    process.env.VERCEL_GIT_COMMIT_SHA ??
    process.env.NEXT_PUBLIC_GIT_COMMIT ??
    "unknown";
  const env = process.env.VERCEL_ENV ?? process.env.NODE_ENV ?? "development";
  const buildTime = process.env.NEXT_PUBLIC_BUILD_TIME ?? "unknown";

  return (
    <footer className="border-t border-gray-800 mt-10 px-6 py-4">
      <div className="max-w-6xl mx-auto flex flex-wrap gap-x-5 gap-y-1 text-[10px] text-gray-600">
        <span>commit {commit.slice(0, 7)}</span>
        <span>api v0.1.0</span>
        <span>ranking formula v2</span>
        <span>inbox calc inbox-v1</span>
        <span>build {buildTime}</span>
        <span>env {env}</span>
      </div>
    </footer>
  );
}
