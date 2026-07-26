import { ApiError } from "@/app/components/ApiError";
import { BoardClient } from "@/app/board/BoardClient";
import { GlobalRole, RegisterCompany, board } from "@/lib/board";

export const dynamic = "force-dynamic";

export default async function BoardPage() {
  let roles: GlobalRole[] = [];
  let register: RegisterCompany[] = [];
  let queued: string[] = [];
  let error: string | null = null;
  try {
    // The queue is fetched here rather than in the client so the board opens
    // already showing what you picked last time. A shortlist that resets on
    // reload is worse than none — it quietly loses decisions.
    [roles, register, queued] = await Promise.all([
      board.roles(300),
      board.register(),
      board.queuedJobIds(),
    ]);
  } catch (e) {
    error = (e as Error).message;
  }

  if (error) return <ApiError error={error} />;
  return <BoardClient roles={roles} register={register} queued={queued} />;
}
