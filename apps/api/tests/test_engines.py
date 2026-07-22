from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.eligibility.engine import CandidateFacts, Verdict, evaluate
from app.ingestion.dedup import DedupKey, is_duplicate
from app.ingestion.freshness import compute_freshness
from app.ingestion.normalize import normalize_company, normalize_title, title_core
from app.parsing.jd_parser import parse_jd
from app.ranking.engine import RankInputs, rank


def _jd(text):
    return parse_jd(text)


def test_jd_parser_extracts_sponsorship_and_degree():
    jd = _jd("Bachelor's degree required. We are unable to provide sponsorship. 3+ years.")
    assert jd.degree_level == "bachelors"
    assert jd.needs_sponsorship_info == "no_sponsorship"
    assert jd.years_experience == 3.0


def test_eligibility_ineligible_on_sponsorship_conflict():
    jd = _jd("We cannot provide visa sponsorship for this position.")
    facts = CandidateFacts(needs_sponsorship=True)
    rep = evaluate(jd, facts)
    assert rep.verdict == Verdict.INELIGIBLE
    assert rep.jd_evidence  # evidence retained
    assert rep.conflicts


def test_eligibility_uncertain_when_unknown_hard_gate():
    jd = _jd("We are unable to offer sponsorship.")
    facts = CandidateFacts(needs_sponsorship=None)  # unknown -> must not guess
    rep = evaluate(jd, facts)
    assert rep.verdict == Verdict.UNCERTAIN
    assert rep.needs_user_confirmation is True


def test_eligibility_eligible_when_all_pass():
    jd = _jd("Bachelor's degree required.")
    facts = CandidateFacts(highest_degree="masters", degree_rank=3)
    rep = evaluate(jd, facts)
    assert rep.verdict in (Verdict.ELIGIBLE, Verdict.LIKELY_ELIGIBLE)


def test_freshness_closed_is_zero():
    assert compute_freshness(
        source_posted_at=datetime.now(UTC),
        last_verified_at=datetime.now(UTC),
        application_deadline=None,
        source_status="closed",
    ) == 0.0


def test_freshness_recent_higher_than_old():
    now = datetime.now(UTC)
    recent = compute_freshness(source_posted_at=now, last_verified_at=now,
                               application_deadline=None)
    old = compute_freshness(
        source_posted_at=now - timedelta(days=60),
        last_verified_at=now - timedelta(days=10),
        application_deadline=None,
    )
    assert recent > old


def test_normalize_and_dedup():
    assert normalize_company("Example Co, Inc.") == "example"
    assert normalize_title("Senior Software Engineer") == "senior software engineer"
    assert "senior" not in title_core("Senior Software Engineer")

    a = DedupKey(canonical_url="https://x/apply")
    b = DedupKey(canonical_url="https://x/apply")
    dup, reason = is_duplicate(a, b)
    assert dup and reason == "same_canonical_url"


def test_dedup_company_title_location():
    a = DedupKey(company_norm="acme", title_core="software engineer", location_key="toronto")
    b = DedupKey(company_norm="acme", title_core="software engineer", location_key="toronto")
    dup, reason = is_duplicate(a, b)
    assert dup and reason == "same_company_title_location"


def test_ranking_is_reproducible_and_explainable():
    jd = _jd("Bachelor's degree required. Python and SQL.")
    facts = CandidateFacts(highest_degree="bachelors", degree_rank=2)
    rep = evaluate(jd, facts)
    inp = RankInputs(
        jd=jd, eligibility=rep,
        candidate_skills={"python", "sql"}, jd_skills={"python", "sql"},
        target_roles={"engineer"}, normalized_title="software engineer",
        remote_mode="remote", preferred_remote="remote", location_ok=True,
        salary_ok=True, freshness_score=0.9, company_quality=0.8,
        estimated_minutes=10, historical_outcome_rate=0.3,
    )
    r1 = rank(inp)
    r2 = rank(inp)
    assert r1.total_score == r2.total_score  # deterministic
    assert 0.0 <= r1.total_score <= 1.0
    assert r1.dimensions and r1.why_recommended
    assert r1.strategy in {"quick", "serious", "manual"}


def test_ranking_ineligible_capped():
    jd = _jd("We cannot provide sponsorship.")
    facts = CandidateFacts(needs_sponsorship=True)
    rep = evaluate(jd, facts)
    inp = RankInputs(
        jd=jd, eligibility=rep, candidate_skills=set(), jd_skills={"python"},
        target_roles=set(), normalized_title="x", remote_mode=None,
        preferred_remote="any", location_ok=None, salary_ok=None,
        freshness_score=0.9, company_quality=None, estimated_minutes=5,
        historical_outcome_rate=None,
    )
    r = rank(inp)
    assert r.total_score <= 0.15
