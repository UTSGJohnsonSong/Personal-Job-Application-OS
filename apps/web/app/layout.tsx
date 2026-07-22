import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Personal Job Application OS",
  description: "First-party job discovery, explainable ranking, assisted applications.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <header className="border-b border-gray-800 px-6 py-4 flex items-center gap-6">
            <span className="font-semibold text-white">Job Application OS</span>
            <nav className="flex gap-4 text-sm text-gray-400">
              <Link href="/" className="hover:text-white">Dashboard</Link>
              <Link href="/inbox" className="hover:text-white">Job Inbox</Link>
            </nav>
            <span className="ml-auto text-xs text-gray-600">
              Every submission requires per-job confirmation
            </span>
          </header>
          <main className="p-6 max-w-6xl mx-auto">{children}</main>
        </div>
      </body>
    </html>
  );
}
