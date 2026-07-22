import Link from "next/link";

import { AmmoBlock, api } from "@/lib/api";

export const dynamic = "force-dynamic";

const CATEGORY_LABELS: Record<string, string> = {
  resume_bullet: "简历 Bullet",
  project: "项目描述",
  skill_combo: "技能组合",
  story: "面试故事 / STAR",
  answer_template: "标准问答模板",
  cover_paragraph: "Cover Letter 段落",
  headline: "一句话定位",
  other: "其他",
};

function Block({ b, isVariant }: { b: AmmoBlock; isVariant?: boolean }) {
  return (
    <div
      className={`rounded border p-3 ${
        isVariant ? "border-gray-800 bg-black/20 ml-6" : "border-gray-700 bg-panel"
      }`}
    >
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm text-white">{b.title}</span>
        {b.is_master ? (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-900">
            母本
          </span>
        ) : (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-900">
            变体{b.direction ? ` · ${b.direction}` : ""}
          </span>
        )}
        {b.contains_metrics && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-900">
            含数字 · 需可核实
          </span>
        )}
        {!b.user_confirmed && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">
            未确认
          </span>
        )}
        {b.usage_count > 0 && (
          <span className="text-[10px] text-gray-500">用过 {b.usage_count} 次</span>
        )}
      </div>
      <p className="text-sm text-gray-300 mt-2 whitespace-pre-wrap">{b.content}</p>
      {b.tags.length > 0 && (
        <div className="flex gap-1 mt-2 flex-wrap">
          {b.tags.map((t) => (
            <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">
              #{t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default async function AmmoPage({
  searchParams,
}: {
  searchParams: Promise<{ category?: string; q?: string }>;
}) {
  const sp = await searchParams;
  let groups: AmmoBlock[] = [];
  let error: string | null = null;
  try {
    groups = (await api.ammo({ category: sp.category, q: sp.q })).groups;
  } catch (e) {
    error = (e as Error).message;
  }

  const byCategory: Record<string, AmmoBlock[]> = {};
  for (const g of groups) {
    (byCategory[g.category] ??= []).push(g);
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-white">弹药库</h1>
        <p className="text-xs text-gray-500 mt-1">
          分类存放可随取随用的材料：1 母本 + N 变体。生成申请材料时只从这里取用组合，不凭空编造。
        </p>
      </div>

      <div className="flex gap-2 flex-wrap">
        <a
          href="/ammo"
          className={`text-xs px-2 py-1 rounded border ${
            !sp.category
              ? "border-accent text-accent"
              : "border-gray-700 text-gray-400 hover:text-white"
          }`}
        >
          全部
        </a>
        {Object.entries(CATEGORY_LABELS).map(([k, label]) => (
          <a
            key={k}
            href={`/ammo?category=${k}`}
            className={`text-xs px-2 py-1 rounded border ${
              sp.category === k
                ? "border-accent text-accent"
                : "border-gray-700 text-gray-400 hover:text-white"
            }`}
          >
            {label}
          </a>
        ))}
      </div>

      {error && (
        <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-4 text-amber-200 text-sm">
          无法读取弹药库（{error}）
        </div>
      )}

      {!error && groups.length === 0 && (
        <div className="text-sm text-gray-400">
          弹药库是空的。可以让我把你 Obsidian 弹药库里的 bullet 母本和变体导进来。
        </div>
      )}

      {Object.entries(byCategory).map(([cat, blocks]) => (
        <section key={cat}>
          <h2 className="text-sm font-semibold text-white mb-2">
            {CATEGORY_LABELS[cat] ?? cat}
            <span className="text-gray-600 font-normal ml-2">{blocks.length}</span>
          </h2>
          <div className="grid gap-2">
            {blocks.map((b) => (
              <div key={b.id} className="space-y-2">
                <Block b={b} />
                {b.variants?.map((v) => (
                  <Block key={v.id} b={v} isVariant />
                ))}
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
