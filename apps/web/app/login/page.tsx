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
  const supplied = String(formData.get("password") ?? "");
  const next = String(formData.get("next") ?? "/");

  // Constant-time-ish compare.
  let diff = supplied.length === password.length ? 0 : 1;
  for (let i = 0; i < Math.max(supplied.length, password.length); i++) {
    diff |= supplied.charCodeAt(i) ^ password.charCodeAt(i);
  }

  if (!password || diff !== 0) {
    failures += 1;
    if (failures >= 5) {
      lockedUntil = now + 5 * 60_000; // 5 minutes
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
          placeholder="Password"
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-100"
        />

        {sp.error === "locked" && (
          <p className="text-xs text-red-400">
            Too many attempts. Try again in a few minutes.
          </p>
        )}
        {sp.error === "1" && (
          <p className="text-xs text-red-400">Incorrect password.</p>
        )}

        <button className="w-full text-sm px-3 py-2 rounded bg-accent text-white hover:opacity-90">
          Sign in
        </button>
      </form>
    </div>
  );
}
