"""Rank the real scanned jobs against the real candidate profile.

Company evidence is taken ONLY from official job-board text (grade A). Nothing
about a company is invented; companies without collected evidence stay Unrated,
which is exactly what the engine should say.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.company.intelligence import (
    CompanyDimension as D,
)
from app.company.intelligence import (
    Evidence,
    SourceGrade,
    assess_company,
)
from app.eligibility.engine import CandidateFacts, evaluate
from app.parsing.jd_parser import parse_jd
from app.ranking.gate import evaluate_gate
from app.ranking.modes import RankingMode, RankingProfile
from app.ranking.priority import compute_priority
from app.roles.taxonomy import classify_role
from app.skills.ontology import CandidateSkillEvidence as CS
from app.skills.ontology import EvidenceStrength as E
from app.skills.ontology import JDSkill, compute_fit, extract_skills

# ---------------------------------------------------------------- candidate
# From the resume only. Work authorization from the user's explicit statement.
FACTS = CandidateFacts(
    highest_degree="bachelors",
    degree_rank=2,
    work_auth_countries={"CA"},
    needs_sponsorship=False,          # Canada PR — user_confirmed
    target_employment_types={"internship", "coop"},
)

# Evidence strength reflects where each skill was actually used.
SKILLS = [
    CS("python", E.PRODUCTION),        # Remeda production + Shell
    CS("postgresql", E.PRODUCTION),    # OMOP CDM warehouse
    CS("sql", E.PRODUCTION),
    CS("fastapi", E.PRODUCTION),       # Remeda service
    CS("django", E.INTERNSHIP),        # WholeViz
    CS("pandas", E.INTERNSHIP),
    CS("numpy", E.INTERNSHIP),
    CS("sklearn", E.PERSONAL_PROJECT), # insurance GLM
    CS("power_bi", E.INTERNSHIP),      # Shell dashboards
    CS("docker", E.LISTED_ONLY),
    CS("git", E.LISTED_ONLY),
    CS("javascript", E.LISTED_ONLY),
    CS("react", E.LISTED_ONLY),        # resume says "basic" — never upgrade this
]

# ------------------------------------------------------------ company evidence
# Verbatim from Cohere's OFFICIAL Ashby posting => grade A, source_type
# "official_ats". Only claims the posting actually makes.
def _ev(dim, val, summary, grade=SourceGrade.A, stype="official_ats"):
    return Evidence(url="https://jobs.ashbyhq.com/cohere", source_type=stype,
                    grade=grade, supports_dimension=dim, summary=summary, value=val)


COHERE_EVIDENCE = [
    _ev(D.TECHNICAL_DENSITY, 0.92,
        "'training and deploying frontier models'; builds foundation AI models"),
    _ev(D.SYSTEM_SCALE, 0.80,
        "'scaling the pods to serve our API'; production API platform"),
    _ev(D.INTERNSHIP_PROGRAM, 0.88,
        "'we don't distinguish much between interns and full-time employees... "
        "plenty of opportunities to push code to production', mentors named"),
    _ev(D.CAREER_OPTIONALITY, 0.85,
        "hiring across Frontend, Backend, Full-stack and Infrastructure teams"),
    _ev(D.BRAND_SIGNAL, 0.70,
        "co-HQ Toronto + San Francisco; offices London, NYC, Montreal, Seoul, "
        "Germany, Paris", SourceGrade.A, "official_site"),
    _ev(D.STABILITY, 0.65,
        "RRSP matching, 401K and pension scheme; 6 weeks paid vacation",
        SourceGrade.B, "official_ats"),
]

# ------------------------------------------------------------------- the jobs
JOBS = [
    ("Cohere", "Software Engineer Intern (Fall / Winter 2026)", COHERE_EVIDENCE,
     "Ship delightful experiences for user-facing products, crafting code for browsers or "
     "server code. Build features for the API platform. Design and implement robust data "
     "pipelines (crawlers, storage, filters). Design and implement scalable services or "
     "infrastructure for machine learning development. Build internal tooling (CI/CD, dev "
     "utilities). Maintain technical documentation. Currently enrolled in a post-secondary "
     "program. Python.", 0.95, 20),
    ("Cohere", "Machine Learning Intern/Co-op (Fall, 2026)", COHERE_EVIDENCE,
     "Design, train and improve upon cutting-edge models. Train extremely large-scale models "
     "on massive datasets. Proficiency in Python and ML frameworks such as Tensorflow, JAX, "
     "and XLA/MLIR. Experience using large-scale distributed training. Familiarity with "
     "autoregressive sequence models such as Transformers. Bonus: CUDA kernels, TPUs, papers "
     "at NeurIPS/ICML.", 0.93, 20),
    ("Deepgram", "Software Engineering Internship (Fall 2026/Summer 2027)", [],
     "Software engineering internship working on speech AI systems, backend services and "
     "production infrastructure. Python.", 0.99, 20),
    ("Stripe", "Software Engineer, New Grad (Toronto)", [],
     "Build and ship production systems. Write code, design systems, deploy to production, "
     "own services. Bachelor's degree.", 0.60, 30),
    ("Waabi", "2026 Intern, PhD Research Scientist", [],
     "Research internship in autonomous driving. PhD required. Publications expected.",
     0.20, 25),
    ("Databricks", "Product Management Intern (Summer 2027)", [],
     "Product management internship. Work with engineering and data teams to define product "
     "requirements, analyze usage data, and drive roadmap decisions. SQL.", 0.70, 25),
]


def main() -> None:
    out = Path(sys.argv[1]) / "real_ranking.txt"
    profile = RankingProfile.for_mode(RankingMode.INTERNSHIP)
    rows = []

    for company, title, evidence, desc, freshness, effort in JOBS:
        jd = parse_jd(desc)
        gate = evaluate_gate(evaluate(jd, FACTS))
        ci = assess_company(evidence)
        role = classify_role(title, desc)
        jd_skills = [JDSkill(s, required=True) for s in extract_skills(desc)]
        fit = compute_fit(jd_skills, SKILLS)
        r = compute_priority(
            gate=gate, company=ci, role=role, fit=fit, description=desc,
            profile=profile, freshness=freshness, effort_minutes=effort,
            has_outcome_history=False,
        )
        rows.append((company, title, r, ci))

    rows.sort(key=lambda x: -x[2].application_priority)

    L = []
    L.append("=" * 104)
    L.append("RANKED JOB LIST — Internship Mode (platform 50% / role 20% / team 12% / fit 10%)")
    L.append("Application Priority is 0-100 PRIORITY. It is NOT a match percentage.")
    L.append("=" * 104)
    L.append("")
    L.append(f"{'#':<3}{'PRIORITY':<10}{'ELIG':<7}{'TIER':<16}{'ROLE':<6}"
             f"{'PLATFORM':<10}{'ROLE-SV':<9}{'FIT':<7}{'COV':<7}{'RECOMMENDATION'}")
    L.append("-" * 104)
    for i, (company, title, r, ci) in enumerate(rows, 1):
        L.append(
            f"{i:<3}{r.application_priority:<10.1f}{r.eligibility.gate.value:<7}"
            f"{ci.display_tier:<16}{r.role_band:<6}"
            f"{r.company_platform_value.conservative:<10.0f}"
            f"{r.role_strategic_value.conservative:<9.0f}"
            f"{r.current_candidate_fit.conservative:<7.0f}"
            f"{r.evidence_coverage*100:<7.0f}{r.recommendation}"
        )
        L.append(f"   {company} — {title}")
        L.append("")

    L.append("=" * 104)
    L.append("DETAIL — why each one ranks where it does")
    L.append("=" * 104)
    for i, (company, title, r, ci) in enumerate(rows, 1):
        L.append("")
        L.append(f"[{i}] {company} — {title}")
        L.append(f"    Eligibility      : {r.eligibility.gate.value}  ({r.eligibility.verdict})")
        L.append(f"    Company Tier     : {ci.display_tier}  status={ci.rating_status}")
        L.append(f"    Evidence         : score={ci.known_evidence_score:.0f}  "
                 f"coverage={ci.evidence_coverage:.0%}")
        L.append(f"    Role Category    : {r.role_band} / {r.role_type}  "
                 f"(transferability {r.transferability})")
        L.append("    --- six scores ---")
        L.append(f"      Company Platform Value : {r.company_platform_value.conservative:6.1f}")
        L.append(f"      Role Strategic Value   : {r.role_strategic_value.conservative:6.1f}")
        fitc = r.current_candidate_fit
        L.append(f"      Current Candidate Fit  : {fitc.conservative:6.1f}"
                 f"   (known {fitc.known_evidence:.0f}, cov {fitc.coverage:.0%})")
        L.append(f"      Team / Project Quality : {r.team_project_quality.conservative:6.1f}")
        L.append(f"      Career Optionality     : {r.career_optionality.conservative:6.1f}")
        L.append(f"      Opportunity Estimate   : {r.opportunity_estimate}")
        L.append("    --- priority build-up ---")
        for k, v in r.contributions.items():
            L.append(f"      {k:<24s} +{v:6.1f}")
        L.append(f"      {'Base Priority':<24s} ={r.base_priority:7.1f}")
        L.append(f"      {'Tier Adjustment':<24s} {r.tier_adjustment:+7.1f}")
        if r.urgency_adjustment:
            L.append(f"      {'Urgency':<24s} {r.urgency_adjustment:+7.1f}")
        if r.floor_applied:
            L.append("      (Tier x Role priority floor applied)")
        L.append(f"      {'FINAL':<24s} ={r.application_priority:7.1f}")
        L.append(f"    Rule             : {r.interaction_rule}")
        for w in r.why[:3]:
            L.append(f"    + {w}")
        for w in r.why_not[:3]:
            L.append(f"    - {w}")
        for u in r.unknowns[:3]:
            L.append(f"    ? {u}")

    out.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
