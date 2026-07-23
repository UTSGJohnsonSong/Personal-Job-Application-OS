import "./globals.css";
import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { signOut } from "@/app/actions";
import { VersionFooter } from "@/app/components/VersionFooter";
import { SESSION_COOKIE, verifySession } from "@/lib/session";

export const metadata: Metadata = {
  title: "Personal Job Application OS",
  description: "First-party job discovery, explainable ranking, assisted applications.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // AUTHORITATIVE session check. This layout runs in the Node runtime, so it
  // always sees APP_SECRET_KEY — unlike the Edge middleware, which is only a
  // cheap pre-filter. Fails closed: no secret => nobody gets in.
  const pathname = (await headers()).get("x-pathname") ?? "";
  const isLogin = pathname === "/login";

  if (!isLogin) {
    const secret = process.env.APP_SECRET_KEY ?? "";
    const token = (await cookies()).get(SESSION_COOKIE)?.value;
    if (!secret || !(await verifySession(token, secret))) {
      redirect("/login?error=session");
    }
  }

  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          {!isLogin && (
            <header className="border-b border-gray-800 px-6 py-4 flex items-center gap-6">
              <span className="font-semibold text-white">Job Application OS</span>
              <nav className="flex gap-4 text-sm text-gray-400">
                <Link href="/" className="hover:text-white">Dashboard</Link>
                <Link href="/pool" className="hover:text-white">Pool</Link>
                <Link href="/priority" className="hover:text-white">Priority</Link>
                <Link href="/queue" className="hover:text-white">Apply Queue</Link>
                <Link href="/records" className="hover:text-white">Applications</Link>
                <Link href="/ammo" className="hover:text-white">Library</Link>
              </nav>
              <span className="ml-auto text-xs text-gray-600">
                Every submission requires per-job confirmation
              </span>
              <form action={signOut}>
                <button className="text-xs text-gray-500 hover:text-white">Sign out</button>
              </form>
            </header>
          )}
          <main className="p-6 max-w-6xl mx-auto">{children}</main>
          {!isLogin && <VersionFooter />}
        </div>
      </body>
    </html>
  );
}
