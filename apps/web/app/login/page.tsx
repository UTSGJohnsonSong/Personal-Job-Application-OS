import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { SESSION_COOKIE, issueSession, sessionCookieOptions } from "@/lib/session";

export const dynamic = "force-dynamic";

// Deliberately coarse rate limiting: this instance has exactly one user, so a
// short global lockout after repeated failures is enough to stop brute force
// without any storage. Resets on cold start, which is acceptable here.
let failures = 0;
let lockedUntil = 0;

async function login(formData: FormData) {
  "use server";

  const now = Date.now();
  if (now < lockedUntil) redirect("/login?error=locked");

  const password = process.env.APP_PASSWORD ?? "";
  const secret = process.env.APP_SECRET_KEY ?? "";
  if (!password || !secret) redirect("/login?error=config");

  const supplied = String(formData.get("password") ?? "");
  const next = String(formData.get("next") ?? "/");

  let diff = supplied.length === password.length ? 0 : 1;
  for (let i = 0; i < Math.max(supplied.length, password.length); i++) {
    diff |= supplied.charCodeAt(i) ^ password.charCodeAt(i);
  }

  if (diff !== 0) {
    failures += 1;
    if (failures >= 5) {
      lockedUntil = now + 5 * 60_000;
      failures = 0;
    }
    redirect("/login?error=1");
  }

  failures = 0;
  const jar = await cookies();
  jar.set(SESSION_COOKIE, await issueSession(secret), sessionCookieOptions);
  redirect(next.startsWith("/") ? next : "/");
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}) {
  const sp = await searchParams;

  // Config presence only — never the values themselves.
  const hasPassword = Boolean(process.env.APP_PASSWORD);
  const hasSecret = Boolean(process.env.APP_SECRET_KEY);
  const configured = hasPassword && hasSecret;

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <form
        action={login}
        className="w-full max-w-sm rounded-lg border border-gray-800 bg-panel p-6 space-y-4"
      >
        <div>
          <h1 className="text-lg font-semibold text-white">Job Application OS</h1>
          <p className="text-xs text-gray-500 mt-1">
            This instance holds personal data. Sign in to continue.
          </p>
        </div>

        <input type="hidden" name="next" value={sp.next ?? "/"} />
        <input
          type="password"
          name="password"
          autoFocus
          required
          disabled={!configured}
          placeholder="Password"
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-100 disabled:opacity-40"
        />

        {sp.error === "locked" && (
          <p className="text-xs text-red-400">
            Too many attempts. Try again in a few minutes.
          </p>
        )}
        {sp.error === "1" && <p className="text-xs text-red-400">Incorrect password.</p>}
        {sp.error === "config" && (
          <p className="text-xs text-red-400">Login is not configured on the server.</p>
        )}

        <button
          disabled={!configured}
          className="w-full text-sm px-3 py-2 rounded bg-accent text-white hover:opacity-90 disabled:opacity-40"
        >
          Sign in
        </button>

        {!configured && (
          <div className="rounded border border-amber-800 bg-amber-950/40 p-3 text-[11px] text-amber-200 space-y-1">
            <div className="font-medium">Setup required — login is not configured.</div>
            <div>
              APP_PASSWORD:{" "}
              <span className={hasPassword ? "text-emerald-400" : "text-red-400"}>
                {hasPassword ? "set" : "MISSING"}
              </span>
            </div>
            <div>
              APP_SECRET_KEY:{" "}
              <span className={hasSecret ? "text-emerald-400" : "text-red-400"}>
                {hasSecret ? "set" : "MISSING"}
              </span>
            </div>
            <div className="text-amber-300/70">
              Add the missing variable(s) to this project&apos;s Production
              environment, then redeploy. Values are never displayed here.
            </div>
          </div>
        )}
      </form>
    </div>
  );
}
