"""Build the candidate's personal-context profile from his own documents.

Every fact here traces to a primary source the candidate supplied — his ACORN
transcript, his resume, or a direct statement he made — and is marked
user_confirmed so the eligibility engine may actually use it. Nothing is
inferred beyond what those documents state.

Why this exists: the database held a fictional seed profile ("Fictional
University", generic skills, no target employment types), so the eligibility
gate had nothing to screen against and passed senior, ten-years-experience
roles to a co-op student. This replaces that with who he actually is.

Sources:
  T = Academic History - ACORN.pdf (accurate as of 2026-07-19)
  R = Zekun Song - Resume.pdf
  U = the candidate's direct statements in this project

Usage:  python scripts/build_candidate.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, select

from app.core.provenance import ProvenanceSource
from app.db.session import SessionLocal
from app.models.personal import (
    ApplicationPreference,
    CandidateEducation,
    CandidateExperience,
    CandidateProfile,
    CandidateProject,
    CandidateSkill,
    WorkAuthorization,
)
from app.models.user import User

REAL_EMAIL = "zekun.song@mail.utoronto.ca"

# Confirmed skills, grouped only for readability. Wording preserved from the
# resume; nothing upgraded ("React/Next.js (basic)" stays basic).
SKILLS: list[tuple[str, str | None]] = [
    ("python", "proficient"), ("pandas", None), ("numpy", None),
    ("sql", "proficient"), ("postgresql", "proficient"),
    ("etl", "proficient"), ("data validation", None),
    ("schema design", None), ("database migrations", None),
    ("power bi", "proficient"), ("data visualization", None),
    ("excel", None), ("powerpoint", None),
    ("fastapi", "proficient"), ("django", "proficient"),
    ("rest apis", None), ("asyncpg", None),
    ("javascript", "basic"), ("react", "basic"), ("next.js", "basic"),
    ("scikit-learn", None), ("machine learning", None),
    ("time series analysis", None), ("statistical modelling", None),
    ("llm application development", None), ("nl-to-sql", None),
    ("neo4j", None), ("git", None), ("docker", None), ("pytest", None),
    ("figma", None), ("omop cdm", None), ("fhir", None),
]

EXPERIENCE = [
    ("University of Toronto — Remeda Clinical AI Platform",
     "Backend & Data Engineer", "2026-04", "present", [
        "Owned the terminology and reference-data layer of an OMOP CDM "
        "PostgreSQL warehouse integrating OpenMRS via FHIR, NLP outputs, and "
        "Synthea/MIMIC-IV datasets.",
        "Integrated 12 vocabularies and 90,000+ codes from UMLS and government "
        "datasets (CIHI, AHRQ, CMS); built a FastAPI/async PostgreSQL service "
        "mapping clinical text to SNOMED CT, ICD-10, RxNorm, LOINC.",
        "Hardened ETL with idempotent reruns, batched SQL writes and "
        "SHA-256-pinned reference data; added 60+ unit tests on a "
        "15+-contributor codebase.",
        "Deployed the backend to production ahead of the CanHealth demo and "
        "co-presented the platform.",
     ]),
    ("Shell", "Data Science Intern", "2024-06", "2024-09", [
        "Delivered an internal analytics web portal for self-serve data access, "
        "cutting ad-hoc data requests by over 50%.",
        "Integrated LLM-based NL-to-SQL with a rule-engine validation layer "
        "(schema grounding, permission checks), 92% pass rate over 300+ queries.",
        "Automated usage reporting, cutting the product feedback cycle from 3 "
        "weeks to 1; built 10+ auto-refreshed Power BI dashboards.",
     ]),
    ("WholeViz (Industry Partner Capstone)",
     "Technical Product Lead — Full-Stack Analytics Platform",
     "2025-09", "2025-12", [
        "Led a 6-person team to ship a full-stack data-analytics platform for "
        "non-technical users, owning backend architecture and delivery.",
        "Built Django + PostgreSQL services with normalized schemas, multi-user "
        "access management and automated ingest/validate pipelines.",
        "Translated non-technical stakeholder requirements into system specs "
        "through agile, design-thinking iterations.",
     ]),
]

PROJECTS = [
    ("Insurance Data Pipeline & Pricing Analysis",
     "End-to-end pipeline over 40,000+ insurance records with a two-part claim "
     "model — logistic regression for occurrence, Gamma GLM for severity — "
     "identifying 4-5x loss differentials and a risk-adjusted pricing "
     "recommendation projected to improve loss ratio ~12% on a hold-out set.",
     ["python", "scikit-learn", "glm", "logistic regression", "pandas"]),
]


def _prov(obj, source: ProvenanceSource, note: str) -> None:
    obj.source = source.value
    obj.provenance = note
    obj.confidence = 1.0
    obj.user_confirmed = True


async def main() -> None:
    async with SessionLocal() as s:
        user = (await s.execute(select(User))).scalars().first()
        if user is None:
            raise SystemExit("no user row exists; run the app once to create one")

        # Reclaim the sole user as the real candidate, keeping the id so every
        # existing score and application stays linked to him.
        user.email = REAL_EMAIL
        uid = user.id

        # Clear the fictional seed rows for this user before loading real ones.
        for model in (CandidateProfile, CandidateEducation, CandidateSkill,
                      WorkAuthorization, ApplicationPreference,
                      CandidateExperience, CandidateProject):
            await s.execute(delete(model).where(model.user_id == uid))

        profile = CandidateProfile(
            user_id=uid,
            headline="CS + Data Science student, backend/data engineering",
            summary="Honours BSc double specialist in Computer Science and Data "
                    "Science at the University of Toronto. Backend and data "
                    "engineering across clinical-AI, energy and capstone work. "
                    "Seeking a Fall 2026 / 2027 co-op.",
            location="Toronto, ON, Canada",
            links={"linkedin": "linkedin.com/in/zekun-song",
                   "email": REAL_EMAIL, "phone": "+1 (647) 829-6198"})
        _prov(profile, ProvenanceSource.RESUME_EXTRACTED, "Resume 2026")
        s.add(profile)

        edu = CandidateEducation(
            user_id=uid, school="University of Toronto (St. George)",
            degree="bachelors",
            field="Computer Science & Data Science (Double Specialist, Honours BSc)",
            start_date="2023-09", end_date="2027-12",
            gpa="3.43 cumulative / 3.87 (2025-26)")
        _prov(edu, ProvenanceSource.IMPORTED_DOCUMENT,
              "ACORN transcript, accurate as of 2026-07-19; degree in progress, "
              "not yet conferred; Dean's List Scholar 2024 Winter")
        s.add(edu)

        # Work authorisation. Canada PR with co-op eligibility; NO US
        # authorisation. The absence of a US row is what makes US-only roles
        # fail the location gate, so it is left absent deliberately.
        auth = WorkAuthorization(
            user_id=uid, country="CA", status="permanent_resident",
            needs_sponsorship=False)
        _prov(auth, ProvenanceSource.USER_CONFIRMED,
              "candidate statement: Canadian PR, co-op eligible, no US work "
              "authorisation (remote-only for US roles)")
        s.add(auth)

        for name, prof in SKILLS:
            sk = CandidateSkill(user_id=uid, name=name, proficiency=prof)
            _prov(sk, ProvenanceSource.RESUME_EXTRACTED, "Resume 2026 skills")
            s.add(sk)

        for company, title, start, end, bullets in EXPERIENCE:
            exp = CandidateExperience(
                user_id=uid, company=company, title=title,
                start_date=start, end_date=end, bullets=bullets)
            _prov(exp, ProvenanceSource.RESUME_EXTRACTED, "Resume 2026")
            s.add(exp)

        for name, desc, tech in PROJECTS:
            proj = CandidateProject(user_id=uid, name=name, description=desc, tech=tech)
            _prov(proj, ProvenanceSource.RESUME_EXTRACTED, "Resume 2026")
            s.add(proj)

        # Preferences. target_employment_types and years_experience are read by
        # the eligibility engine; setting them is what lets it screen seniority.
        pref = ApplicationPreference(
            user_id=uid,
            locations=["Toronto, ON", "Greater Toronto Area", "Canada",
                       "Remote (Canada)"],
            remote_pref="any",
            industries=["fintech", "health", "ai", "data"],
            # Ordered by his own preference analysis: analyst first, then
            # product, then DS/engineering.
            target_roles=["Data Analyst", "Product Analyst", "Data Scientist",
                          "Technical Product Manager", "Associate Product Manager",
                          "Software Engineer", "Machine Learning Engineer",
                          "Backend Engineer", "Data Engineer"],
            dealbreakers=["requires US work authorization",
                          "requires security clearance"],
            weight_overrides={
                "target_employment_types": ["internship", "co_op", "new_grad"],
                # A co-op student with three internships behind him. This is the
                # denominator the experience gate compares a JD's requirement to.
                "years_experience": 1,
                # He is targeting early-career roles; anything mid-level or above
                # is out of reach this cycle.
                "target_seniority": ["intern", "co_op", "new_grad", "entry"],
                "coop_window": "2026-09 to 2027-04 (8-month), open 4-12 months",
            })
        _prov(pref, ProvenanceSource.USER_CONFIRMED,
              "preference analysis (10_GradWork_Decision) + resume co-op "
              "availability")
        s.add(pref)

        await s.commit()

    print(f"built candidate profile for {REAL_EMAIL}")
    print(f"  {len(SKILLS)} skills, {len(EXPERIENCE)} roles, {len(PROJECTS)} projects")
    print("  target employment: internship / co-op / new-grad")
    print("  work auth: CA permanent resident, co-op eligible, no US")


if __name__ == "__main__":
    asyncio.run(main())
