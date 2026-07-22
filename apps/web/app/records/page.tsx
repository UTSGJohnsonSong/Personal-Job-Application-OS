import Link from "next/link";

import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function RecordsPage() {
  let items: Awaited<ReturnType<typeof api.records>>["items"] = [];
  let error: string | null = null;
  try {
    items = (await api.records()).items;
  } catch (e) {
    error = (e as Error).message;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-white">投递记录</h1>
        <p className="text-xs text-gray-500 mt-1">
          每一份申请：用了哪版简历、每个问题怎么答的、状态时间线。点进去展开。
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-4 text-amber-200 text-sm">
          无法读取记录（{error}）
        </div>
      )}

      {!error && items.length === 0 && (
        <div className="text-sm text-gray-400">还没有任何申请记录。</div>
      )}

      <div className="grid gap-2">
        {items.map((r) => (
          <Link
            key={r.application_id}
            href={`/records/${r.application_id}`}
            className="rounded-lg border border-gray-800 bg-panel p-4 hover:border-gray-600 block"
          >
            <div className="flex items-center gap-3">
              <span className="text-white">{r.title}</span>
              <span className="text-xs px-2 py-0.5 rounded border border-gray-700 bg-gray-800 text-gray-300">
                {r.status}
              </span>
              {r.submitted_at && (
                <span className="text-xs text-gray-500">
                  投于 {new Date(r.submitted_at).toLocaleDateString()}
                </span>
              )}
              <span className="ml-auto text-xs text-gray-600">展开 →</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
