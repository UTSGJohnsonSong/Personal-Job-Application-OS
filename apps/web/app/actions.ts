"use server";

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api";
import { API, apiHeaders } from "@/lib/pool";

export async function changeStatus(formData: FormData) {
  const id = String(formData.get("application_id"));
  const status = String(formData.get("status"));
  await api.setStatus(id, status);
  revalidatePath(`/records/${id}`);
  revalidatePath("/records");
  revalidatePath("/queue");
}

export async function queueAdd(formData: FormData) {
  const jobId = String(formData.get("job_id"));
  await api.addToQueue(jobId);
  revalidatePath("/inbox");
  revalidatePath("/queue");
}

export async function queueRemove(formData: FormData) {
  const jobId = String(formData.get("job_id"));
  await api.removeFromQueue(jobId);
  revalidatePath("/queue");
  revalidatePath("/inbox");
}

/**
 * Recording that one role was preferred over another. Kept because the
 * pairwise signal feeds the ranking engine, even though the compare page it
 * was built for is gone — the job detail page is where it belongs next.
 */
export async function recordPreference(formData: FormData) {
  const { scoring } = await import("@/lib/scoring");
  await scoring.preference(
    String(formData.get("chosen")),
    String(formData.get("rejected")),
  );
  revalidatePath("/inbox");
}

/**
 * Score postings that have none yet, a slice at a time.
 *
 * Scoring the whole pool takes minutes, which is longer than a proxy will hold
 * a request open, so the caller asks for a slice and loops on `remaining`.
 * Because it only touches unscored rows, an interrupted run is resumed simply
 * by calling again — nothing is redone.
 */
export async function scorePending(limit = 400): Promise<{
  scored: number;
  remaining: number;
  failed: string[];
}> {
  const res = await fetch(`${API}/scoring/recompute`, {
    method: "POST",
    cache: "no-store",
    headers: apiHeaders(),
    body: JSON.stringify({ only_unscored: true, limit }),
  });
  if (!res.ok) throw new Error(`scoring/recompute -> ${res.status}`);
  const d = await res.json();
  revalidatePath("/board");
  revalidatePath("/inbox");
  return { scored: d.scored ?? 0, remaining: d.remaining ?? 0, failed: d.failed ?? [] };
}

export async function signOut() {
  const { cookies } = await import("next/headers");
  const { SESSION_COOKIE } = await import("@/lib/session");
  const { redirect } = await import("next/navigation");
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
}

// Refreshing the inbox is driven by the Refresh button, which polls
// /api/refresh for progress. Nothing here needs a server action any more —
// the old rebuild/compare actions belonged to pages that no longer exist.
