import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { SESSION_COOKIE, verifySession } from "@/lib/session";

/**
 * Gates the ENTIRE app behind a login.
 *
 * Without this, the site holds the API token server-side and would happily
 * render the owner's personal data to any visitor who knows the URL.
 *
 * The middleware only needs APP_SECRET_KEY (to verify the session cookie).
 * The password check lives in the login server action, which runs in the Node
 * runtime — so this file never depends on APP_PASSWORD being visible to the
 * Edge runtime. It still fails closed: with no secret, no cookie can ever
 * verify, so every request is sent to /login.
 */
export async function middleware(request: NextRequest) {
  if (request.nextUrl.pathname === "/login") return NextResponse.next();

  const secret = process.env.APP_SECRET_KEY ?? "";
  const ok = secret
    ? await verifySession(request.cookies.get(SESSION_COOKIE)?.value, secret)
    : false;

  if (ok) return NextResponse.next();

  const url = new URL("/login", request.url);
  url.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
