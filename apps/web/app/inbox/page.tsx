import { redirect } from "next/navigation";

/**
 * The Job Inbox is now company-tier-centric: Tier -> Company -> top roles.
 * The old flat list showed a bare freshness percentage with no company context,
 * so it is retired rather than kept running alongside the new views.
 */
export default function InboxPage() {
  redirect("/companies");
}
