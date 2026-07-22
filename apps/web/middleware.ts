import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { SESSION_COOKIE, verifySession } from "@/lib/session";

/**
 * Gates the ENTIRE app behind a login.
 *
 * Without this, the site holds the API token server-side and would happily
 * render the owner's personal data to any visitor who knows the URL.
 */
export async function middleware(request: NextRequest) {
  const secret = process.env.APP_SECRET_KEY ?? "";
  const password = process.env.APP_PASSWORD ?? "";

  // Fail closed: with no password configured, refuse rather than serve data.
  if (!password || !secret) {
    if (request.nextUrl.pathname === "/setup-required") return NextResponse.next();
    return NextResponse.rewrite(new URL("/setup-required", request.url));
  }

  const ok = await verifySession(request.cookies.get(SESSION_COOKIE)?.value, secret);
  if (ok) return NextResponse.next();

  if (request.nextUrl.pathname === "/login") return NextResponse.next();

  const url = new URL("/login", request.url);
  url.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(url);
}

export const config = {
  // Everything except Next internals and static assets.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
