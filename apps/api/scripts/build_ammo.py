"""Load the candidate's 弹药库 (application-material library) from Obsidian.

The Obsidian vault at `D:\\A. Obsidian\\03 事业\\01 求职系统\\弹药库\\` is the
source of truth: every bullet there already carries a finalized LaTeX form,
a fact anchor, and (for the risky ones) a defense line for follow-up
questions. This script carries the *current* set — the ⭐/定稿 entries — into
AmmoBlock rows so `/ammo` in the app stops being empty.

Deliberately excluded, and why:
  - "旧版存档" / "已归档" bullets — superseded by a later compressed version
    (e.g. Remeda's old B1-B4 were merged into the 2026-07-18 four-bullet set).
  - Fidelity Investments and Nanjing Yilian Sunshine projects — the user
    already decided to drop them (timeline conflict / low value).
  - "在建" (in-progress) items — not done, so not real yet.
  - The honours line — the award name isn't confirmed.
Importing those would put unverified or retracted claims in front of the
eligibility/application-drafting flow as if they were ready to use.

Usage:  python scripts/build_ammo.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, select

from app.core.provenance import ProvenanceSource
from app.db.session import SessionLocal
from app.models.ammo import AmmoBlock
from app.models.user import User


def _prov(obj: AmmoBlock, note: str) -> None:
    obj.source = ProvenanceSource.USER_CONFIRMED.value
    obj.provenance = note
    obj.confidence = 1.0
    obj.user_confirmed = True


# (category, title, content, tags, direction, contains_metrics, notes, provenance)
BLOCKS: list[tuple[str, str, str, list[str], str | None, bool, str | None, str]] = [
    # --- Remeda (data-engineering core narrative), 2026-07-18 four-bullet
    # compressed final. Supersedes all older B1-B4 drafts in the same file.
    ("resume_bullet", "Clinical Data Warehousing",
     r"\resumeItem{Clinical Data Warehousing}"
     r"{Owned the terminology and reference-data layer of an OMOP CDM "
     r"PostgreSQL warehouse integrating OpenMRS data via FHIR APIs, NLP "
     r"outputs, and Synthea and MIMIC-IV datasets.}",
     ["remeda", "data-engineering", "backend"], "data-engineering", False,
     "边界：平台主干是别人的，主语只能是从句里的定语，我的动词只有 'owned the "
     "terminology layer'。Epic 已删——平台只有 FHIR translator 模块，无真实 Epic "
     "环境连接证据。追问口径：被问 Epic/MIMIC → 'those are sibling workstreams; "
     "mine is the terminology layer every one of them depends on'",
     "弹药库/01_Remeda_弹药.md B0，2026-07-18 四条结构定稿"),
    ("resume_bullet", "Terminology Standardization",
     r"\resumeItem{Terminology Standardization}"
     r"{Integrated \textbf{12} vocabularies and 90,000+ codes via API, "
     r"bulk-load, and ETL pipelines; built a FastAPI/async PostgreSQL "
     r"service mapping unstructured clinical text to SNOMED CT, ICD-10, "
     r"RxNorm, and LOINC.}",
     ["remeda", "data-engineering", "etl"], "data-engineering", True,
     "锚点：12 = ATC/NDC/DSM-5/LOINC-FR-CA/SNOMED-CA/OHIP/ICD-10-CA/CCI/"
     "HCPCS/ICF/CCS/MDC；90k = CIHI 20,323 入库 + AHRQ 72,446 crosswalk。"
     "追问防线：三条架构分别举一个标准为例（HCPCS→API、CIHI→bulk loader、"
     "MDC→ETL 阶段）",
     "弹药库/01_Remeda_弹药.md B0，2026-07-18 四条结构定稿"),
    ("resume_bullet", "Data Integrity & Reliability (Remeda)",
     r"\resumeItem{Data Integrity \& Reliability}"
     r"{Protected production data quality by validating values against "
     r"CMS specifications and blocking an underdetermined metric; hardened "
     r"ETL with idempotent reruns, batched SQL writes, SHA-256-pinned "
     r"data, and \textbf{60+} unit tests.}",
     ["remeda", "data-engineering", "banking"], "data-engineering", True,
     "⭐银行岗必带。锚点：DRG descope = PR #211（对照 CMS FY2026 v43.1 逐条验证 "
     "MDC）；60+ tests = #211:20 + #173:19 + #198:16 + #209:6 + #208:4。"
     "超页裁剪顺序：先删 'on a 15+-contributor codebase'",
     "弹药库/01_Remeda_弹药.md B0，2026-07-18 四条结构定稿"),
    ("resume_bullet", "Production Debugging & Demo",
     r"\resumeItem{Production Debugging \& Demo}"
     r"{Resolved a production deployment failure before the CanHealth "
     r"industry demo by tracing a backend-origin misconfiguration, "
     r"deploying and validating the fix, and co-presenting the platform.}",
     ["remeda", "data-engineering", "debugging"], "data-engineering", False,
     "锚点：Remada/32（curl 四路径交叉验证、X-Vercel-Error、git 考古到 "
     "ec2.env）。⚠️ 'resolved/deploying/co-presenting' 为 2026-07-16 本人口述"
     "补充（档案记录止于 07-11），面试口径按实际发生说",
     "弹药库/01_Remeda_弹药.md B0，2026-07-18 四条结构定稿"),
    # --- Shell (DA/BI narrative core) ---
    ("resume_bullet", "Internal Web Portal",
     r"\resumeItem{Internal Web Portal}"
     r"{Delivered an end-to-end internal analytics web portal enabling "
     r"self-serve data access for business users, cutting ad-hoc data "
     r"requests by \textbf{over 50\%} (16 to 7 per week).}",
     ["shell", "data-analyst", "internship"], "data-analyst", True,
     "⭐DA版首选。锚点：RAW_04 'ad-hoc 数据请求从约16次/周降至约7次/周'。用词开关："
     "JD 说 portal 用 portal，说 application 用 application",
     "弹药库/02_Shell_弹药.md B1"),
    ("resume_bullet", "NL-to-SQL Validation",
     r"\resumeItem{NL-to-SQL Validation}"
     r"{Integrated LLM-based NL-to-SQL generation with a rule-engine "
     r"validation layer (schema grounding, permission checks) against a "
     r"production database --- \textbf{92\%} pass rate across 300+ test "
     r"queries.}",
     ["shell", "internship", "llm"], None, True,
     "⭐两版通用。⚠️ 边界：92% 是整系统通过率，我的角色是集成与打通（RAW 自述：团队"
     "环境+已有项目），动词只能用 Integrated 不能用 Implemented/Built",
     "弹药库/02_Shell_弹药.md B2"),
    ("resume_bullet", "Data Logging & Automation",
     r"\resumeItem{Data Logging \& Automation}"
     r"{Designed query-logging and user-behavior analytics modules and "
     r"automated usage reporting, reducing the product--feedback cycle "
     r"from \textbf{3 weeks to 1 week}.}",
     ["shell", "internship", "automation"], None, True,
     "2026-07-17 定稿。备用长版含 '~30 daily interactions'（数字小，默认不用）；"
     "'3x' 与 '3 weeks to 1 week' 二选一，不叠加",
     "弹药库/02_Shell_弹药.md B3"),
    ("resume_bullet", "Dashboards & Reporting",
     r"\resumeItem{Dashboards \& Reporting}"
     r"{Built 10+ automatically refreshed Power BI dashboards connected to "
     r"SQL pipelines for internal KPI reporting, replacing recurring "
     r"manual reporting workflows.}",
     ["shell", "data-analyst", "bi"], "data-analyst", True,
     "⭐DA版加重，2026-07-17 定稿。⚠️ 'real-time' 已降级为 'automatically "
     "refreshed'——除非用户确认当时是 DirectQuery/streaming/push dataset，否则不"
     "用 real-time；'eliminating' 降为 'replacing recurring'",
     "弹药库/02_Shell_弹药.md B4"),
    # --- WholeViz (leadership + stakeholder narrative) ---
    ("resume_bullet", "Full-Stack Development (WholeViz)",
     r"\resumeItem{Full-Stack Development}"
     r"{Led a \textbf{6}-person team to design and ship a full-stack data "
     r"analytics web platform for non-technical users, owning backend "
     r"architecture and delivery from requirements to industry-partner "
     r"handoff.}",
     ["wholeviz", "leadership", "capstone"], None, True,
     "⭐领导力担当。裁剪规则：空间不足时 WholeViz 先于 Shell/Remeda 被压缩，"
     "但这条(B1)和 B3 保留（领导力+沟通是它的独特价值）",
     "弹药库/03_WholeViz_弹药.md B1"),
    ("resume_bullet", "Backend & Data Automation (WholeViz)",
     r"\resumeItem{Backend \& Data Automation}"
     r"{Designed Django + PostgreSQL backend services with normalized "
     r"schema design, multi-user access management, and automated "
     r"pipelines that ingested, validated, and stored event data.}",
     ["wholeviz", "capstone", "backend"], None, False,
     "⚠️ 禁写 'role-based access control'——档案只支撑多用户，撑不起角色层。"
     "裁剪规则：空间不足时先删这条（与 Remeda 的后端叙事重叠）",
     "弹药库/03_WholeViz_弹药.md B2"),
    ("resume_bullet", "Stakeholder Communication (WholeViz)",
     r"\resumeItem{Stakeholder Communication}"
     r"{Partnered with an industry stakeholder through agile, "
     r"design-thinking iterations to define product workflows and "
     r"translate non-technical requirements into system specifications.}",
     ["wholeviz", "capstone", "leadership"], None, False,
     "⭐JD含agile/design thinking时必带。agile / design thinking 是为 RBC 类 "
     "JD 埋的词；JD 没有这两词时可换回朴素版",
     "弹药库/03_WholeViz_弹药.md B3"),
    # --- Projects ---
    ("project", "Insurance Data Pipeline & Pricing Analysis",
     r"\resumeProjectHeading{\textbf{Insurance Data Pipeline \& Pricing "
     r"Analysis} --- Predictive Modeling}{Feb. 2026 -- Mar. 2026}"
     "\n"
     r"\projectItem{Built an end-to-end data pipeline on 40,000+ insurance "
     r"records, covering ingestion, cleaning, feature engineering, and a "
     r"frequency-severity model (logistic regression + Gamma GLM) "
     r"identifying risk factors with 4--5x loss differentials.}"
     "\n"
     r"\projectItem{Turned model outputs into a pricing recommendation "
     r"projected to improve loss ratio by \textbf{$\sim$12\%} on a "
     r"hold-out test set.}",
     ["insurance", "finance", "modeling"], None, True,
     "⭐金融岗必带。锚点：RAW_04（40,000+ 保单；hold-out 验证；4-5x 损失差异）。"
     "追问防线：12% 是 hold-out 模拟推算不是实盘；两阶段=频率(logistic)×严重度"
     "(Gamma GLM)。repo: github.com/UTSGJohnsonSong/CAS_Case_Study",
     "弹药库/04_Projects_弹药.md，现役"),
    # --- Skills (two parallel master combos, not variants of each other) ---
    ("skill_combo", "Skills — Data Engineering (组合A)",
     r"\item \textbf{Data \& ETL:} Python (Pandas, NumPy), SQL (PostgreSQL: "
     r"query design, schema \& migrations), ETL pipelines, structured \& "
     r"unstructured ingestion (APIs, web scraping, flat files), automated "
     r"reporting"
     "\n"
     r"\item \textbf{BI \& Visualization:} Power BI (10+ production "
     r"dashboards), data visualization, MS Excel, PowerPoint"
     "\n"
     r"\item \textbf{Web \& Backend:} FastAPI, Django, RESTful APIs, async "
     r"Python (asyncio, asyncpg), TypeScript/JavaScript (ES6+), Java; "
     r"React/Next.js (basic)"
     "\n"
     r"\item \textbf{Analytics \& AI Systems:} LLM application development "
     r"(OpenAI API), NL-to-SQL pipelines, Scikit-learn, Neo4j"
     "\n"
     r"\item \textbf{Tools \& Practices:} Git \& GitHub (PR-based workflow), "
     r"Docker, pytest, Vercel, Stripe \& Supabase integration, Figma",
     ["skills", "data-engineering"], "data-engineering", False,
     "现役，RBC 定向。禁写清单（永久）：FAISS｜DRG（作为已交付）｜"
     "role-based access control（WholeViz）｜LangChain/RAG｜任何未做过的算法/框架",
     "弹药库/05_Skills_组合.md 组合A"),
    ("skill_combo", "Skills — Data/Product Analyst (组合B)",
     r"\item \textbf{Analytics \& BI:} Power BI (10+ production "
     r"dashboards), interactive visualization (Plotly, Leaflet), MS Excel, "
     r"PowerPoint, statistical modelling (GLM, time series)"
     "\n"
     r"\item \textbf{Data \& SQL:} Python (Pandas, NumPy), R (tidyverse, R "
     r"Markdown), SQL (PostgreSQL), ETL pipelines, web scraping \& API "
     r"data acquisition, automated reporting"
     "\n"
     r"\item \textbf{AI Systems:} LLM application development (OpenAI "
     r"API), NL-to-SQL pipelines, Scikit-learn"
     "\n"
     r"\item \textbf{Tools:} Git \& GitHub, Docker, pytest, Figma",
     ["skills", "data-analyst"], "data-analyst", False,
     "BI 前置，统计加重。statistical modelling (GLM, time series) 有课程+"
     "Insurance 项目支撑；R / Plotly / Leaflet / web scraping / GitHub Pages "
     "项目站 = JSC370 全程",
     "弹药库/05_Skills_组合.md 组合B"),
    # --- Header / Education ---
    ("headline", "Header / Contact Line",
     r"Toronto, ON, Canada $|$ +1 (647) 829-6198 $|$ "
     r"\href{mailto:zekun.song@mail.utoronto.ca}"
     r"{\underline{zekun.song@mail.utoronto.ca}} $|$ "
     r"\href{https://linkedin.com/in/zekun-song}"
     r"{\underline{linkedin.com/in/zekun-song}}",
     ["header"], None, False,
     "待办：LinkedIn 链接验证；GitHub 建好后插入第四项",
     "弹药库/06_Education_头部模块.md 页头"),
    ("other", "Education — DE order",
     r"\textbf{University of Toronto (St. George)}\hfill Toronto, ON, "
     r"Canada, Sep. 2023 -- Dec. 2027 (Expected)\\"
     "\n"
     r"\item Honours Bachelor of Science, Double Specialist in Computer "
     r"Science and Data Science"
     "\n"
     r"\item GPA: 3.87/4.00, 2025--26 academic year; 4.00/4.00 Winter "
     r"session"
     "\n"
     r"\item Relevant Courses: Databases, Data Science, Statistical "
     r"Modelling, Machine Learning, Time Series Analysis",
     ["education", "data-engineering"], "data-engineering", True,
     "GPA 口径：面试被问 cGPA 如实答 'cumulative ~3.4-3.5, but my full "
     "2025-26 year was 3.87 with a 4.00 final term'。co-op 岗强烈建议加回可用"
     "性声明：Available for an 8-month co-op work term (Sep. 2026 -- Apr. 2027)",
     "弹药库/06_Education_头部模块.md Education 区，DE 版课程顺序"),
    ("other", "Education — DA order",
     r"\textbf{University of Toronto (St. George)}\hfill Toronto, ON, "
     r"Canada, Sep. 2023 -- Dec. 2027 (Expected)\\"
     "\n"
     r"\item Honours Bachelor of Science, Double Specialist in Computer "
     r"Science and Data Science"
     "\n"
     r"\item GPA: 3.87/4.00, 2025--26 academic year; 4.00/4.00 Winter "
     r"session"
     "\n"
     r"\item Relevant Courses: Statistical Modelling, Time Series "
     r"Analysis, Data Science, Databases, Machine Learning",
     ["education", "data-analyst"], "data-analyst", True,
     "统计前置的课程顺序，其余同 DE 版",
     "弹药库/06_Education_头部模块.md Education 区，DA 版课程顺序（统计前置）"),
]


async def main() -> None:
    async with SessionLocal() as s:
        user = (await s.execute(select(User))).scalars().first()
        if user is None:
            raise SystemExit("no user row exists; run the app once to create one")
        uid = user.id

        await s.execute(delete(AmmoBlock).where(AmmoBlock.user_id == uid))

        for category, title, content, tags, direction, has_metrics, notes, prov in BLOCKS:
            block = AmmoBlock(
                user_id=uid, category=category, title=title, content=content,
                tags=tags, direction=direction, contains_metrics=has_metrics,
                notes=notes,
            )
            _prov(block, prov)
            s.add(block)

        await s.commit()
        print(f"loaded {len(BLOCKS)} ammo blocks")


if __name__ == "__main__":
    asyncio.run(main())
