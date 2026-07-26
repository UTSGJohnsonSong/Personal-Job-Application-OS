# 重建方案 — 岗位池 + 申请状态

> 日期：2026-07-25
> 依据：三个 code-explorer 只读审计 + 数据库实查
> 状态：待 Zekun 确认

---

## 0. 结论摘要

你要的两个页面，**后端基本都已经有了**，缺的是查询参数和前端。

但在做任何页面之前必须先修三个 bug，否则页面上每个数字都是错的。

你提的「先公司排名、再公司内岗位排名」——**你自己的代码库两个月前就把这个问题解决了**，而且结论和我独立想出来的一样：公司 tier 管分组，application priority 管排序，两个视图同一份数据。两个视图的后端都写好了，前端一个都没调。

---

## 1. 必须先修的三个 bug

### Bug 1 — 评分行重复 10 倍（阻断性）

**现象：** 10,921 个岗位，111,166 条评分行，平均每岗位 10.2 条。同一岗位的不同行带着**互相矛盾的 eligibility 结论**（PASS+REVIEW+FAIL 去重后加起来 14,178 > 10,923）。

**根因（已定位）：** `apps/api/app/services/scoring_v2.py:183-218` 里是裸的 `session.add()`——每次调用插一条新行，不查旧行、不 upsert、不 delete-before-insert。

而 `ApplicationPriorityScore`（`models/ranking_v2.py:93-142`）**没有任何唯一约束**。对比 `CompanyRoleRanking` 有 `uq_role_rank(user_id, job_id)`，而且 `rebuild_inbox` 会先删后插（`inbox.py:271-276`）——`ApplicationPriorityScore` 不在那个删除列表里。

`score_all_jobs` 由两处触发：`POST /scoring/recompute` 和每次 `POST /pool/refresh`。跑 10 次就是 10 倍。10.18x 完全对得上。

**为什么现在还能用：** 所有读取方都自己取「按 created_at 最新的那条」（`scoring_v2.py:250-251`、`inbox.py:74-83`、`pool.py:60-68`）。靠客户端兜底掩盖了问题。

**修法：**
1. 加唯一约束 `(job_id, user_id, ranking_mode)` + Alembic migration
2. `score_job` 改成 upsert
3. 一次性清理脚本：每组只保留最新一条

### Bug 2 — 同一岗位的资格结论会在两次评分间翻转

**根因：** `scoring_v2.py:149-153` 取岗位地点时用了 `.limit(1)` 但**没有 `.order_by()`**：

```python
location = (await session.execute(
    select(JobLocation.raw_text).where(JobLocation.job_id == job.id).limit(1)
)).scalar_one_or_none()
```

`JobLocation` 对 `job_id` 没有唯一约束——多城市岗位有多行。没有排序，返回哪一行不保证稳定（Postgres 上尤其）。而地点是**硬性资格检查**，多伦多 vs 迪拜会直接翻转 PASS/FAIL。

**修法：** 加确定性排序（按 id 或按「加拿大优先」），或者改成读取全部地点再判断——多地岗位本来就该按「任一地点可投即可投」处理。

### Bug 3 — successfactors 连接器丢地点

1,378 个岗位里 968 个没有 `JobLocation` 行（70%）。其它连接器全是 0%。

没有地点 → 硬性检查返回 unknown → 判 REVIEW → 推回给你人工看。这是 REVIEW 队列的主要来源。

**修法：** 补 successfactors 的地点字段映射。

---

## 2. 你的两级筛选逻辑：评价

### 结论：结构对，但它是**配额**，不是**排序**

如果先按公司排、每家取前 N，会系统性错过好岗位：

```
Geotab      (A 级)  岗位优先级  67.6 · 65.1 · 63.4
Cloudflare  (B 级)  岗位优先级  68.0
```

每家取前 2，A 级先看 → 你会先看 Geotab 的 67.6 和 65.1，才轮到 Cloudflare 的 68.0。全池最好的那个被挤到后面。

### 你的代码库已经写死了正确答案

`portfolio.py:1-11`：

> Company Tier organises COMPANIES.
> Application Priority orders ROLES.
> Tier is therefore a grouping axis, **never a hard ceiling**: an A-tier role at priority 94 outranks an S-tier role at 84 in the global queue.

`portfolio.py:205-212`（`global_priority_queue` 文档字符串）：

> Tier is displayed but **must NOT group or cap this list** — that is the whole point of "company-centric management, opportunity-centric ranking".

`portfolio.py:291-308`（统一阈值的理由）：

> 每档单独设阈值会把 tier 信号算第二遍，产生「71 分的 S 级岗位显示 Backup，63 分的 A 级岗位显示 Recommended」这种矛盾。

**两个视图的后端都已经写好：**
- `group_by_tier()` — 按公司分组（视图 1）
- `global_priority_queue()` — 纯按优先级的平铺队列，完全忽略 tier（视图 2）
- 路由也有：`/inbox/by-tier`、`/inbox/global`

**前端一个都没调。** 现在的 `/inbox` 只用了 `/pool`，也就是只有视图 1。

### 方案（2026-07-25 Zekun 定稿）：两个页面都做

不是二选一。两个视图，**同一份数据、同一个投递清单、同一套配额**。

| 页面 | 排序依据 | 回答的问题 |
|---|---|---|
| **A. 机会流**（全局） | 纯 `application_priority`，忽略 tier | 「全池最值得投的是哪些」 |
| **B. 公司册**（分组） | 公司按 tier 排，岗位在公司内按 priority 排 | 「这家公司我该投哪几个」 |

两个页面的后端**已经写好了**：`global_priority_queue()`（`portfolio.py:205-220`）和 `group_by_tier()`（`portfolio.py:188-202`），路由是 `/inbox/global` 和 `/inbox/by-tier`。前端从未调用过。

**必须共享的三样东西：**

1. **投递清单** — 从任一页面加入，进的都是同一个 `Application.queued_at` 队列
2. **配额** — 在 A 页加了 Geotab 的岗位，B 页的 Geotab 卡片上配额同步扣减
3. **裁决结果** — 在任一页把某个 REVIEW 判成可投，两边都生效

**为什么两个都要：**
- A 页防止你系统性错过 B 级公司的好岗位（那是纯全局排序的作用）
- B 页对应你真实的取舍动作——「这家投几个」是按公司做的决定，不是按岗位

| 层 | 作用 |
|---|---|
| 排序 | A 页只认 `application_priority`；B 页公司间按 tier、公司内按 priority |
| 配额 | 每家公司一个名额上限，两页共享，加入清单时扣减 |
| 分组 | 是**视图**，不是排序方式——两页数据同源 |

**配额上限按公司在招岗位数定，不按 tier 定**（tier 已经在分数里算过一遍）：

| 该公司在招岗位数 | 建议上限 |
|---|---|
| 1–3 | 1 |
| 4–15 | 2 |
| 16+ | 3–4，且要求分属不同部门 |

小公司一个 recruiter 收你三份申请是减分的；大厂不同团队不同 recruiter，投 3 个没问题。**这是公司规模问题，不是公司好坏问题。**

**交互：** 从全局列表往下走，看到合适的加入清单。某公司配额用完，剩余岗位**变灰但不消失**，标一句「Geotab 已选 2 个」。你仍可强行加——只是知道自己在花什么。

（不消失符合你自己的原则：`inbox/[key]/page.tsx:208` —「Kept visible so the absence is auditable」）

---

## 3. 页面 A / B：岗位池（两个视图）

### 现有的筛选（以及一个真 bug）

| 筛选项 | 计算在哪 | 生效在哪 | 问题 |
|---|---|---|---|
| 资格 FAIL | 评分时 | `relevant_roles` 的 Python 过滤 | 正常 |
| R4 岗位（销售/客服/HR） | — | **只在 `select_company_roles`** | ⚠️ `global_priority_queue` 和 `group_by_tier` **不过滤** |
| 已过截止日期 | — | **只在 `select_company_roles`** | ⚠️ 同上 |
| 来源已关闭 | 评分时降分 | 只在队列页给个 warning | 不排除 |

**这是个真 bug：** 昨天就截止的岗位、纯销售岗，现在会出现在全局队列和公司卡片里，只有「Recommended/Backup」那一块过滤了。做统一浏览页之前必须先统一。

### API 缺什么

现有端点**没有任何筛选参数**：
- `GET /pool` — 零参数
- `GET /scoring/jobs` — 只有 `limit`（≤300），无 offset、无筛选、排序写死在 Python 里
- `GET /jobs` — 有 `limit`/`offset`，但不 join 评分表，拿不到优先级
- `GET /inbox/global` — 只有 `limit`

**需要新增一个端点**（建议在 `/inbox/global` 基础上扩展，因为它已经把公司和岗位平铺在一起了）：

```
GET /pool/roles
  筛选  eligibility · company_tier · role_band · min_priority
        in_canada · deadline_before · company_key · already_applied · source_status
  排序  sort=priority|freshness|posted_at|deadline &  order=asc|desc
  分页  limit & offset
```

**架构成本要说清楚：** `build_pool`、`load_companies`、`score_all_jobs` 现在都是把整张 jobs 表读进内存再用 Python 过滤排序（`pool.py:49-105`、`inbox.py:66-172`）。加筛选参数如果只在 API 层做，等于在这个内存全量扫描上打补丁。真要做好得把过滤下推到 SQL——这是一次实打实的重构，不是加几个参数。

**建议：** 第一版接受内存过滤（1 万行规模够用），但在代码里标明这是已知债务。

### 三个区

| 区 | 内容 | 默认 |
|---|---|---|
| **可选** | PASS，按 priority 全局排序 | 展开 |
| **待裁决** | REVIEW，**按原因分组，不按岗位分组** | 折叠 |
| **已排除** | FAIL，带原因 | 折叠 |

**「待裁决」的批量交互是高杠杆点：**

```
729 个岗位的地点写着 "2 Locations"，系统读不出来。
这通常表示多地招聘。要按可投处理吗？    [ 是 ]  [ 否 ]  [ 逐个看 ]
```

答一次清掉 729 个。比逐个看快三个数量级，决定权仍然在你。

### 投递清单已经存在

`Application.queued_at` 不为空 = 在清单里（`models/application.py:53-54`，代码注释里就叫「想投列表」）。

- 加入：`POST /queue/{job_id}`（幂等，`discovered → saved`，写审计日志）
- 移除：`DELETE /queue/{job_id}`（置空 `queued_at`，不删行）
- 排序：手动优先级 > 分数 > 新鲜度（`queue.py:142-146`）
- 已有「来源已关闭」的 warning 机制（`queue.py:148-153`）

**不需要新建东西，接上就行。**

---

## 4. 页面 2：申请状态与指标

### 状态模型现状

20 个状态（`state_machine.py:6-27`），但**只有 `submitted` 一个是被强制校验的**。

`records.py:276-315` 这个通用改状态接口**根本不调状态机的转换表**——直接赋值。所以 `interview`、`rejected`、`offer` 可以从任意状态跳到任意状态，没有图校验。

**这未必要修**（单用户工具，灵活反而好用），但你得知道那张转换表目前是装饰性的。

### 现在就能算的指标

| 指标 | 数据来源 | 状态 |
|---|---|---|
| 各状态计数 | `Application.status` | 已实现 |
| 漏斗 | 同上 | 已实现，**但有 bug**（见下） |
| 三个转化率 | 同上 | **后端算好了，前端一行没渲染** |
| 本周投递 / 超两周无动静 | `submitted_at` | 已实现 |
| 各阶段耗时 | `ApplicationEvent.occurred_at` + from/to | 数据在，**没人算** |
| 按简历版本 | `packet_id → resume_version_id` | 可 join，没做 |
| 按来源连接器 | `job_id → source_id → connector_key` | 可 join，没做 |
| 按公司 tier | `job_id → company_id → CompanyScoreVersion` | 可 join，没做 |

**已有 bug：** `dashboard.py:18-21` 的 `_FUNNEL` 里有 `eligible` 和 `shortlisted` 两个阶段，**它们不在状态枚举里**，永远显示 0。

### 必须新增的：渠道字段

**全代码库搜 `channel` 零命中。** 系统只记录岗位**怎么发现的**（greenhouse / lever / manual_entry），不记录你**怎么投的**。

你最想看的那个对比——内推 vs 直投——现在算不出来。

**修法（选便宜的）：** 在 `ApplicationEvent.detail` 这个现成的 JSON 字段里记 channel。不用改表。
枚举：`direct | referral | school_portal | linkedin_easy_apply | recruiter_outreach`

### 历史数据的硬限制

你那 50 份投递、3 个回复，**能导入但时间戳全是今天**：

- `manual.py` 只能单条录入，没有批量接口，`ManualJobIn` 没有「我实际投递的日期」字段
- `submitted_at` 只有确认流程会写
- 所有状态变更一律盖 `datetime.now(UTC)`，`ApplicationEvent.occurred_at` 也是

**后果：**
- 那 3 个回复的「投递到回复几天」**永远算不出来**
- 一次性导入 50 份会污染「本周投递」和「超两周无动静」

**唯一准确的做法是绕过 API 直接写库**，手工填真实日期。50 条，值得做——否则你的漏斗从第一天起就是假的。

### 诚实原则

样本不够时不显示比率，显示「n=3，样本不足」。这是你自己的规矩（`不伪造精度`）。

---

## 5. MCP 联动

### 现状：12 个工具，没有 submit

不暴露 submit 是**故意的**，代码里三处写明（`server.py:8-9`、`:182-184`、`README.md:51-55`），而且 API 层也拦（`records.py:294-298` 返回 409）。

### 缺的工具（后端全都有，只差包装）

| 我需要读 | 现有端点 | MCP 有吗 |
|---|---|---|
| 六维分数 + why | `GET /scoring/jobs/{id}` | ❌ |
| 公司档案（tier/value/access/posture） | `GET /registry/company/{key}` | ❌ |
| **你确认过的个人档案** | `GET /personal` | ❌ **最关键的缺口** |
| 岗位池 | `GET /pool` | ❌ |
| 触发刷新 | `POST /pool/refresh` | ❌ |

**「个人档案读不到」意味着我现在写 why-us 是闭着眼写的**——不知道你确认过哪些技能、哪些经历能用。不补这个，我拼的材料你每次都得大改。

全部只需要在 `apps/mcp/server.py` 加 `@mcp.tool()` 包装，不动后端。

### 一个必须修的 provenance bug

`records.py:35`：`AnswerIn.source: str = "user_confirmed"` —— **默认值**。

而 MCP 的 `record_application`（`server.py:135-142`）参数里**根本没有 `source`**，answer 字典原样透传。所以我写的答案如果没显式标 source，会被存成 `user_confirmed=True`——**AI 生成的内容被标记成你确认过的**。

这直接违反你的红线第 2、3 条。

**修法：** MCP 层强制所有 AI 写入的答案标 `source="generated_draft"`（`add_ammo` 已经这么做了，`server.py:121`）。

真正拦住 AI 材料的不是这个字段，是 `guard_submit()` 的 packet_hash 绑定——而且 MCP 连 `/applications/*` 都没包装，结构上够不到 submitted。但标签错了仍然是错的：你在确认页上会看到「你已确认」而其实没有。

---

## 6. 分期

| 期 | 内容 | 前置 |
|---|---|---|
| **P0** | 修 Bug 1/2/3；统一 R4 和过期过滤 | 无 |
| **P1** | 新增 `GET /pool/roles`（筛选+排序+分页）；MCP 补 5 个只读工具 + 修 provenance | P0 |
| **P2a** | **页面 A 机会流**——全局排序、三区、批量裁决、加入清单 | P1 |
| **P2b** | **页面 B 公司册**——公司分组、岗位内嵌、配额显示 | P2a（复用同一套组件和清单逻辑） |
| **P3** | 渠道字段；历史 50 份直接写库导入 | 无（可并行） |
| **P4** | 页面 C 状态与指标（含现成但没渲染的转化率、各阶段耗时） | P3 |

**P2a 先于 P2b**：机会流是更难的那个（筛选、排序、分页、批量裁决都在它上面），公司册基本是同一批组件换个分组方式。反过来做要返工。

**P0 不做完，后面全是假数据。**

---

## 7. 未决 / 需要你拍板

1. **历史 50 份要不要直接写库？** 这是绕过 API 的操作，我建议做，但要你点头。
2. **状态机转换表要不要真正强制？** 现在是装饰性的。单用户工具下宽松可能更好用。
3. **`docs/COMPANY_INBOX.md` 不存在**，但 `portfolio.py:3` 引用了它。是删了还是没写？
4. **仓库是 public。** 已提交的东西都公开了——包括 262 家公司的评级和你的 override 理由。要不要转 private？
5. **权重文档三处不一致**（Obsidian 笔记 50%、`docs/INTERNSHIP_RANKING.md` 50%、代码 38%）。哪份算权威？
6. **`ranking/engine.py` 是死代码**（旧 9 维引擎，只有 seed 和测试引用）。标 deprecated 还是留着？
