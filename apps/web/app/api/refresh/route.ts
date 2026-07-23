import { NextResponse } from "next/server";

import { API, apiHeaders } from "@/lib/pool";

// Proxy so the refresh can be driven from the browser without the API token
// ever reaching it. The token stays on the server; the client only ever talks
// to this route.
export const dynamic = "force-dynamic";

export async function POST() {
  const res = await fetch(`${API}/pool/refresh`, {
    method: "POST",
    headers: apiHeaders(),
    cache: "no-store",
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function GET() {
  const res = await fetch(`${API}/pool/refresh/status`, {
    headers: apiHeaders(),
    cache: "no-store",
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
