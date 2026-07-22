"use server";

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api";

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

export async function recomputeScores() {
  const { scoring } = await import("@/lib/scoring");
  await scoring.recompute("internship");
  revalidatePath("/rankings");
  revalidatePath("/");
}

export async function recordPreference(formData: FormData) {
  const { scoring } = await import("@/lib/scoring");
  const chosen = String(formData.get("chosen"));
  const rejected = String(formData.get("rejected"));
  await scoring.preference(chosen, rejected);
  revalidatePath("/compare");
  revalidatePath("/rankings");
}
