import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { SESSION_COOKIE, verifySession } from "@/lib/session";

/**
 * First line of the login gate.
 *
 * The AUTHORITATIVE check lives in the root layout, which runs in the Node
 * runtime and therefore always sees APP_SECRET_KEY. This middleware is a cheap
 * pre-filter: it bounces requests that carry no cookie at all, and passes the
 * pathname along so the layout knows whether to enforce.
 *
 * It never *grants* access on its own — a forged cookie still fails the Node
 * verification in the layout.
 */
export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const headers = new Headers(request.headers);
  headers.set("x-pathname", pathname);

  if (pathname === "/login") {
    return NextResponse.next({ request: { headers } });
  }

  const cookie = request.cookies.get(SESSION_COOKIE)?.value;
  if (!cookie) {
    const url = new URL("/login", request.url);
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  // If the Edge runtime can see the secret we can reject bad cookies early;
  // if it cannot, we defer to the Node-side check rather than guessing.
  const secret = process.env.APP_SECRET_KEY ?? "";
  if (secret && !(await verifySession(cookie, secret))) {
    const url = new URL("/login", request.url);
    url.searchParams.set("error", "session");
    return NextResponse.redirect(url);
  }

  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
