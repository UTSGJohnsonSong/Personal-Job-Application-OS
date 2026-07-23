"""Company registry — two-pass tiering for one specific candidate.

How a tier is produced
----------------------
Pass 1 (algorithm): every company carries eight declared inputs on a 0-3 scale.
`platform_score` and `personal_score` turn them into two numbers, which band
into two provisional tiers. This pass is mechanical and reproducible.

Pass 2 (judgment): where the algorithm lands somewhere I disagree with, the
profile carries an explicit `override` plus `override_reason`. Nothing moves
silently — a test asserts every override states its reason, so the two passes
can always be diffed against each other.

Why brand is scored on three separate axes
------------------------------------------
Reach was previously measured as "how many world regions is this employer
hiring in", which scored a Canada-only company like Wealthsimple 0.2/1.0 on
brand — structurally unable to rank well however strong it is here. What
actually matters for this candidate is recognition in Canada (where he works),
the US (where the next job might be) and China (where he is from and may
return). So brand is `brand_ca` / `brand_us` / `brand_cn`, weighted to Canada.

Who is in the registry at all
-----------------------------
Only employers this candidate would plausibly join. A company he would never
work at is not rated low — it is not rated. `EXCLUSIONS` records those with a
reason, so an omission is auditable rather than an accident of which ATS the
connectors happen to support.

Candidate constraints this encodes, taken from his own preference analysis:
  * Role order: Data/Product Analyst > Technical PM/APM > DS at a
    FinTech/HealthTech startup.
  * Explicitly avoid pure data-analyst seats at large firms with no customer
    contact — they generate no founding muscle. That is what `role_floor` marks.
  * Domains that compound for him: clinical AI and health, fintech, applied
    ToB AI.
  * His real bottleneck is getting interviews at all, so a mature, published
    student programme is worth more than a marginally better brand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Provenance(StrEnum):
    ALGORITHM = "algorithm"          # pass 1 stood; no judgment applied
    JUDGMENT_OVERRIDE = "judgment"   # pass 2 moved it, reason recorded
    USER_OVERRIDE = "user_override"  # the candidate overruled both


class Posture(StrEnum):
    """How to act on a company, given how its value and access diverge."""

    BALANCED = "balanced"              # apply normally
    WORTH_FORCING = "worth_forcing"    # worth more than it is reachable:
                                       # referral, cold outreach, keep watching
    FLOOR_ONLY = "floor_only"          # reachable but low value: never let it
                                       # displace a real target


# Below this, an offer is not worth taking on the company's merits alone — the
# specific role would have to carry it. Calibrated so that the floor-only
# public-sector employers fall below and every genuine platform clears it.
OFFER_ACCEPT_THRESHOLD = 50.0

# A company is only a floor option if its value is genuinely low, not merely
# lower than how easy it is to reach.
FLOOR_VALUE_CEILING = 62.0


# Platform and personal scores have different distributions, so they cannot
# share one set of cut points. Platform is anchored absolutely: 88 is the most
# that recognition plus a student programme can earn, so S genuinely means
# "engineering reputation on top of that". Personal bands are set from the
# observed spread across the registry, tuned to keep each tier a usable size —
# a tier holding a third of the list tells him nothing.
TIER_BANDS: tuple[tuple[float, str], ...] = (
    (88.0, "S"), (70.0, "A"), (55.0, "B"), (38.0, "C"), (0.0, "D"),
)
PERSONAL_BANDS: tuple[tuple[float, str], ...] = (
    (84.0, "S"), (76.0, "A"), (66.0, "B"), (56.0, "C"), (0.0, "D"),
)

# Technical reputation is an ADDITIVE bonus, not a reweighting. A company that
# is well known in Canada and runs a stable co-op programme has already earned
# an A on those merits alone; engineering reputation is what lifts a company
# above that, and its absence never drags one below it.
TECH_BONUS_PER_POINT = 4.0


# A floor option must never outrank a real target, however reachable it is.
SAFETY_NET_CEILING = "B"
# Companies he named himself as first and second choices. His stated preference
# outranks the score, which cannot see referrals, programme shape or intent.
NAMED_TIER1_FLOOR = "A"
NAMED_TIER2_FLOOR = "B"

_TIER_ORDER = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}


def _at_least(tier: str, floor: str) -> str:
    return floor if _TIER_ORDER[tier] > _TIER_ORDER[floor] else tier


def _at_most(tier: str, ceiling: str) -> str:
    return ceiling if _TIER_ORDER[tier] < _TIER_ORDER[ceiling] else tier


def band(score: float,
         bands: tuple[tuple[float, str], ...] = TIER_BANDS) -> str:
    for floor, tier in bands:
        if score >= floor:
            return tier
    return "D"


@dataclass(frozen=True)
class CompanyProfile:
    key: str
    name: str
    # -- pass 1 inputs, all 0-3 ------------------------------------------
    brand_ca: int      # recognition and pull inside Canada
    brand_us: int      # recognition in the US market
    brand_cn: int      # recognition in China
    depth: int         # size of the real Canadian technology/data organisation
    role: int          # availability of analyst / product / DS roles he can win
    domain: int        # fit with health, fintech or applied ToB AI
    founder: int       # customer contact, sales visibility, cofounder pool, equity
    program: int       # maturity of the published co-op / internship programme
    why: str
    # Engineering reputation among engineers, independent of consumer fame.
    # Defaults to 1 ("ordinary"), so it only ever needs stating when it matters.
    tech: int = 1
    # Marks a floor option: high interview probability, low career leverage.
    # These exist so the pipeline always has something applicable, and they are
    # never allowed to displace a real target.
    safety_net: bool = False
    # -- pass 2 ---------------------------------------------------------
    override: str | None = None
    override_personal: str | None = None
    override_reason: str | None = None
    # -- identity -------------------------------------------------------
    aliases: tuple[str, ...] = ()
    boards: tuple[tuple[str, str], ...] = ()
    role_floor: bool = False          # brand must not lift a non-technical seat
    tags: tuple[str, ...] = field(default_factory=tuple)
    assessed_on: str = "2026-07-22"
    valid_until: str = "2027-07-22"

    # ---------------- pass 1 ----------------
    @property
    def brand(self) -> float:
        return (self.brand_ca * 0.60 + self.brand_us * 0.25
                + self.brand_cn * 0.15) / 3.0

    @property
    def platform_score(self) -> float:
        """The company on its own terms: is this a place worth having worked?

        Recognition plus a real student programme caps out at 88 — an A. Only
        engineering reputation carries a company into S, and a company with none
        still keeps everything it earned on the other two.
        """
        base = 72.0 * self.brand + 16.0 * (self.program / 3.0)
        return min(100.0, base + TECH_BONUS_PER_POINT * self.tech)

    @property
    def value_score(self) -> float:
        """What the experience is worth once he is actually inside.

        This is the number for an OFFER decision, where reachability has
        already resolved. Nothing here asks whether he can get in.
        """
        return 100.0 * (
            0.30 * self.brand
            + 0.25 * self.tech / 3.0
            + 0.25 * self.domain / 3.0
            + 0.20 * self.founder / 3.0
        )

    @property
    def access_score(self) -> float:
        """How reachable the company actually is for him.

        Every input here is a probability term. They belong together and
        nowhere near the value terms — an earlier version averaged all six
        into one number, which meant "hard to get into" and "not worth much"
        were indistinguishable in the output.
        """
        return 100.0 * (
            0.40 * self.depth / 3.0
            + 0.40 * self.role / 3.0
            + 0.20 * self.program / 3.0
        )

    @property
    def personal_score(self) -> float:
        """Application priority: the geometric mean of value and access.

        Geometric, not arithmetic, because an application is only worth making
        when BOTH hold. An arithmetic mean scores a trivially reachable but
        worthless employer the same as a balanced one — which is exactly how
        floor options used to climb into A and had to be capped by hand.
        """
        return (self.value_score * self.access_score) ** 0.5

    @property
    def algo_tier(self) -> str:
        return band(self.platform_score)

    @property
    def algo_personal_tier(self) -> str:
        return band(self.personal_score, PERSONAL_BANDS)

    # ---------------- pass 2 ----------------
    @property
    def platform_tier(self) -> str:
        return self.override or self.algo_tier

    @property
    def personal_tier(self) -> str:
        """Algorithm, then two structural corrections, then explicit override.

        Both corrections exist because the score has known blind spots:

        * It reads company size, so a small company he named himself as a first
          choice lands in C purely for being small. His stated preference is
          evidence about him, not noise to be averaged away — it sets a floor.
        * It cannot see that a floor option is a floor option. A safety net that
          climbs into A would displace a real target in the recommended set,
          which is the one thing it must never do — so it gets a ceiling.
        """
        if self.override_personal:
            return self.override_personal
        tier = self.algo_personal_tier
        if "tier1" in self.tags:
            tier = _at_least(tier, NAMED_TIER1_FLOOR)
        elif "tier2" in self.tags:
            tier = _at_least(tier, NAMED_TIER2_FLOOR)
        if self.safety_net:
            tier = _at_most(tier, SAFETY_NET_CEILING)
        return tier

    @property
    def provenance(self) -> Provenance:
        if self.override or self.override_personal:
            return Provenance.JUDGMENT_OVERRIDE
        return Provenance.ALGORITHM

    @property
    def adjusted(self) -> bool:
        return (self.platform_tier != self.algo_tier
                or self.personal_tier != self.algo_personal_tier)

    @property
    def posture(self) -> Posture:
        """What to DO about this company, which a single tier cannot express.

        Two companies can share a personal tier for opposite reasons: one is
        hard to reach but worth a lot, the other is easy to reach and worth
        little. They call for different actions, so the split is surfaced
        rather than averaged away.
        """
        gap = self.value_score - self.access_score
        # A gap alone is not enough. Access saturates at 100 for most large
        # employers, so a strong company like Amazon reads as a large negative
        # gap while being nothing like a floor option. Being easy to reach is
        # not the same as being worth little, so FLOOR_ONLY also requires the
        # value itself to be low in absolute terms.
        if gap <= -15.0 and self.value_score < FLOOR_VALUE_CEILING:
            return Posture.FLOOR_ONLY
        if gap >= 20.0 and self.value_score >= OFFER_ACCEPT_THRESHOLD:
            return Posture.WORTH_FORCING
        return Posture.BALANCED

    @property
    def worth_taking_if_offered(self) -> bool:
        """An offer decision uses value alone; access has already resolved."""
        return self.value_score >= OFFER_ACCEPT_THRESHOLD

    @property
    def value_tier(self) -> str:
        return band(self.value_score, VALUE_BANDS)

    @property
    def adjustment_reason(self) -> str | None:
        """Why the final tier differs from what the algorithm produced.

        The structural rules move tiers too, not just explicit overrides, and
        a row marked "adjusted" with no explanation cannot be audited — so the
        rules state themselves here rather than only in code.
        """
        if not self.adjusted:
            return None
        if self.override_reason:
            return self.override_reason
        if self.safety_net and self.algo_personal_tier != self.personal_tier:
            return ("Floor rule: a safety net is capped at tier "
                    f"{SAFETY_NET_CEILING} so it can never displace a real "
                    "target in the recommended set, however reachable it is.")
        if "tier1" in self.tags:
            return ("Floor rule: he named this a first-choice target. The score "
                    "reads company size, so a small named company lands low for "
                    "being small — his stated preference is evidence about him, "
                    "not noise, so it sets a floor of "
                    f"{NAMED_TIER1_FLOOR}.")
        if "tier2" in self.tags:
            return ("Floor rule: he named this a second-choice target, which "
                    f"sets a floor of {NAMED_TIER2_FLOOR}.")
        return None

    @property
    def value_view_action(self) -> str:
        """What the value ranking is telling him to DO about this company.

        Without this the value list reads as a second queue to apply into,
        which would send applications at companies that will not answer.
        """
        if self.posture is Posture.WORTH_FORCING:
            return "referral_or_outreach"     # applying cold will not reach it
        if self.access_score >= 70.0:
            return "already_in_apply_queue"
        return "watch"


def C(key: str, name: str, *, ca: int, us: int, cn: int, depth: int, role: int,
      domain: int, founder: int, prog: int, why: str, tech: int = 1,
      safety_net: bool = False, override: str | None = None,
      override_personal: str | None = None, reason: str | None = None,
      aliases: tuple[str, ...] = (), boards: tuple[tuple[str, str], ...] = (),
      role_floor: bool = False, tags: tuple[str, ...] = ()) -> CompanyProfile:
    return CompanyProfile(
        key=key, name=name, brand_ca=ca, brand_us=us, brand_cn=cn, depth=depth,
        role=role, domain=domain, founder=founder, program=prog, why=why,
        tech=tech, safety_net=safety_net, override=override,
        override_personal=override_personal, override_reason=reason,
        aliases=aliases, boards=boards, role_floor=role_floor, tags=tags)


# =========================================================================
# Named first-choice targets, taken directly from his own preference analysis.
# =========================================================================
_NAMED_TARGETS: list[CompanyProfile] = [
    C("wealthsimple", "Wealthsimple", ca=3, us=1, cn=0, depth=3, role=3, domain=3,
      founder=3, prog=2, tech=3,
      why="His own number-one target. Canada's strongest consumer fintech brand, "
          "real product-analyst and DS co-op seats in Toronto, and the Shell NLQ "
          "work maps directly onto self-serve data products.",
      boards=(("ashby", "wealthsimple"),), tags=("fintech", "toronto", "tier1")),
    C("rbc", "RBC", ca=3, us=1, cn=1, depth=3, role=3, domain=2, founder=2, prog=3, tech=2,
      why="Amplify is a build-something-real innovation internship rather than a "
          "reporting seat — the one bank programme that fits a product builder. "
          "He also has a warm referral here.",
      override_personal="S",
      reason="The algorithm cannot see the referral, nor that Amplify is a "
             "product programme rather than a bank analyst seat. Both matter "
             "more to him than the brand gap to the other banks.",
      aliases=("Royal Bank of Canada", "RBC Amplify"),
      tags=("bank", "toronto", "tier1")),
    C("scotiabank", "Scotiabank", ca=3, us=0, cn=1, depth=3, role=3, domain=2,
      founder=1, prog=3,
      why="Velocity is a structured, well-published data-analyst internship that "
          "opens in September. His own notes call it the stable safety net.",
      boards=(("successfactors", "https://jobs.scotiabank.com"),),
      tags=("bank", "toronto", "tier1")),
    C("shopify", "Shopify", ca=3, us=3, cn=1, depth=3, role=3, domain=2,
      founder=3, prog=3, tech=3,
      why="Canada's flagship technology employer, with a dedicated Engineering "
          "and Data internship stream and genuine commerce-product exposure.",
      tags=("canada", "tier1", "commerce")),
    C("layer6", "Layer 6 AI", ca=2, us=1, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=2, tech=2,
      why="Named in his Tier 2. TD's Toronto applied-AI lab — real ML research "
          "attached to a bank's data, one of the few places that combines both.",
      aliases=("Layer6", "TD Layer 6"), tags=("ai", "toronto", "bank", "tier2")),
    C("borealisai", "Borealis AI", ca=2, us=1, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=2, tech=2,
      why="RBC's Toronto AI research institute: strong applied-ML work and a "
          "recognised Canadian AI brand, hiring separately from RBC's bank roles.",
      tags=("ai", "toronto", "bank")),
    C("exiger", "Exiger", ca=1, us=2, cn=0, depth=2, role=2, domain=3, founder=3,
      prog=1,
      why="Named in his Tier 2. ToB AI for supply-chain and financial risk — a "
          "true enterprise-AI seat where he would see procurement and sales.",
      tags=("ai", "tob", "toronto", "tier2")),
    C("bioadvance", "BioAdvance", ca=1, us=0, cn=0, depth=1, role=2, domain=3,
      founder=3, prog=1,
      why="Named in his Tier 1. HealthTech DS work where the CSC494 diagnostic "
          "pathway research is a genuine differentiator rather than a footnote.",
      tags=("health", "toronto", "tier1")),
]

# =========================================================================
# Toronto and Canadian clinical AI / health tech — his sharpest domain edge.
# =========================================================================
_HEALTH: list[CompanyProfile] = [
    C("uhn", "University Health Network", ca=3, us=1, cn=0, depth=2, role=2,
      domain=3, founder=2, prog=2,
      why="Canada's largest research hospital network. His notes name UHN's "
          "innovation arm as a direct route to clinical buyers — the access "
          "asset he currently lacks for a HealthTech founding path.",
      tags=("health", "toronto", "research")),
    C("sickkids", "SickKids", ca=3, us=1, cn=1, depth=2, role=2, domain=3,
      founder=2, prog=2,
      why="Major paediatric research hospital with real clinical-data and "
          "research-analyst roles, and a named target in his market analysis.",
      tags=("health", "toronto", "research")),
    C("thinkresearch", "Think Research", ca=1, us=0, cn=0, depth=2, role=2,
      domain=3, founder=3, prog=1,
      why="Named in his HealthTech founder path. Toronto clinical-workflow "
          "software — exactly the procurement-failure vantage point he wants.",
      tags=("health", "toronto", "tob")),
    C("pockethealth", "PocketHealth", ca=1, us=1, cn=0, depth=2, role=2, domain=3,
      founder=3, prog=1, tech=2,
      why="Toronto medical-imaging platform with real patient-data engineering, "
          "small enough that a co-op sees the whole product and its buyers.",
      tags=("health", "toronto")),
    C("signal1", "Signal 1", ca=1, us=0, cn=0, depth=1, role=2, domain=3,
      founder=3, prog=1, tech=2,
      why="Toronto clinical-AI startup deploying models inside hospitals — the "
          "closest commercial analogue to his Remeda diagnostic-pathway work.",
      tags=("health", "toronto", "ai")),
    C("pentavere", "Pentavere", ca=1, us=0, cn=0, depth=1, role=2, domain=3,
      founder=3, prog=1, tech=2,
      why="Toronto clinical-AI company extracting structured evidence from "
          "medical records; directly adjacent to his research project.",
      tags=("health", "toronto", "ai")),
    C("bluedot", "BlueDot", ca=2, us=1, cn=1, depth=1, role=2, domain=3,
      founder=2, prog=1, tech=2,
      why="Toronto epidemic-intelligence company with a strong public story: "
          "health data plus real modelling work at a small scale.",
      tags=("health", "toronto", "ai")),
    C("benchsci", "BenchSci", ca=2, us=1, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=2, tech=2,
      why="Toronto applied-AI company for life-sciences research; well funded, "
          "a recognised local AI employer, and it hires students.",
      boards=(("lever", "benchsci"),), tags=("health", "toronto", "ai")),
    C("deepgenomics", "Deep Genomics", ca=2, us=1, cn=0, depth=1, role=1,
      domain=3, founder=1, prog=1, tech=2,
      why="Toronto AI-for-genomics research company, elite in its niche, though "
          "most roles assume graduate-level biology.",
      tags=("health", "toronto", "ai")),
    C("pointclickcare", "PointClickCare", ca=2, us=2, cn=0, depth=3, role=3,
      domain=3, founder=2, prog=2, tech=2,
      why="Large Ontario health-tech platform with genuine analyst and data "
          "roles at co-op scale: high interview probability and a clinical-data "
          "domain match at the same time.",
      boards=(("lever", "pointclickcare"),), tags=("health", "toronto")),
    C("alayacare", "AlayaCare", ca=1, us=1, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=2,
      why="Montreal and Toronto home-care software with real data work and a "
          "recurring co-op intake.",
      tags=("health", "canada")),
    C("league", "League", ca=1, us=1, cn=0, depth=2, role=2, domain=3, founder=2,
      prog=1,
      why="Toronto digital-health platform selling to enterprise benefits "
          "buyers: ToB health with a visible sales motion.",
      tags=("health", "toronto", "tob")),
    C("wellhealth", "WELL Health", ca=2, us=1, cn=0, depth=2, role=2, domain=3,
      founder=1, prog=1,
      why="One of Canada's larger public digital-health companies; broad "
          "clinical-data footprint, less distinctive engineering culture.",
      tags=("health", "canada")),
    C("maple", "Maple", ca=2, us=0, cn=0, depth=1, role=2, domain=3, founder=2,
      prog=1,
      why="Named in his HealthTech path. Canadian telehealth with consumer scale "
          "and a team small enough that a co-op touches real product decisions.",
      tags=("health", "toronto")),
    C("medstack", "MedStack", ca=1, us=0, cn=0, depth=1, role=1, domain=3,
      founder=3, prog=0,
      why="Named in his notes for PHIPA compliance infrastructure — the exact "
          "regulatory gap he identified for a HealthTech founding path.",
      tags=("health", "toronto", "tob")),
    C("vertohealth", "Verto Health", ca=1, us=0, cn=0, depth=1, role=2, domain=3,
      founder=2, prog=1,
      why="Toronto health-data integration company working directly against "
          "hospital systems.",
      tags=("health", "toronto")),
    C("dialogue", "Dialogue Health", ca=1, us=0, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=1,
      why="Montreal virtual-care platform with a real data team and enterprise "
          "customers.",
      tags=("health", "canada")),
    C("benchling", "Benchling", ca=0, us=2, cn=0, depth=1, role=2, domain=3,
      founder=2, prog=2, tech=2,
      why="Life-sciences R&D data platform; strong fit with his biomedical data "
          "background, though Canadian hiring is thin.",
      boards=(("greenhouse", "benchling"),), tags=("health", "tob")),
]

# =========================================================================
# Canadian AI and applied ToB AI — the second domain that compounds for him.
# =========================================================================
_AI: list[CompanyProfile] = [
    C("cohere", "Cohere", ca=3, us=2, cn=1, depth=3, role=2, domain=3, founder=3,
      prog=2, tech=3,
      why="Toronto-headquartered frontier AI company, named in his Tier 2. The "
          "strongest Canadian AI brand he can realistically reach, and its "
          "enterprise motion is exactly the ToB AI exposure he lacks.",
      override_personal="S",
      reason="The algorithm marks it down because analyst-track seats are "
             "scarce. For a Toronto candidate building an applied-AI founding "
             "thesis, the network value alone justifies the top band.",
      boards=(("ashby", "cohere"),), tags=("ai", "toronto", "tier2")),
    C("vectorinstitute", "Vector Institute", ca=3, us=1, cn=1, depth=2, role=2,
      domain=3, founder=2, prog=3, tech=2,
      why="Toronto AI research institute with published applied-AI internships "
          "and unmatched local AI network value — which attacks his actual "
          "bottleneck of not getting interviews at all.",
      tags=("ai", "toronto", "research")),
    C("ada", "Ada", ca=2, us=1, cn=0, depth=2, role=2, domain=3, founder=3,
      prog=2, tech=2,
      why="Toronto ToB conversational-AI company: enterprise customers, a "
          "visible sales cycle, and a product built on exactly the "
          "LLM-plus-guardrails pattern he shipped at Shell.",
      tags=("ai", "toronto", "tob")),
    C("waabi", "Waabi", ca=2, us=1, cn=1, depth=2, role=1, domain=2, founder=1,
      prog=1, tech=3,
      why="Toronto autonomous-driving research company with exceptional "
          "technical density; most postings are PhD-gated, so access is limited.",
      boards=(("lever", "waabi"),), tags=("ai", "toronto")),
    C("tenstorrent", "Tenstorrent", ca=2, us=2, cn=1, depth=2, role=1, domain=1,
      founder=1, prog=2, tech=3,
      why="Toronto AI-silicon company doing deep systems work. Prestigious "
          "locally, but far from his analyst and product strengths.",
      boards=(("greenhouse", "tenstorrent"),), tags=("ai", "toronto", "hardware")),
    C("samsungai", "Samsung AI Centre Toronto", ca=1, us=1, cn=2, depth=1, role=1,
      domain=2, founder=1, prog=2, tech=2,
      why="Toronto industrial AI research lab, recognisable in China through the "
          "Samsung name, though research roles favour graduate students.",
      aliases=("SAIT Toronto",), tags=("ai", "toronto", "research")),
    C("huawei", "Huawei Canada", ca=1, us=0, cn=3, depth=3, role=2, domain=2,
      founder=1, prog=2, tech=2,
      why="Large Toronto and Ottawa R&D presence and a top-tier brand in China, "
          "which matters if he ever returns. Weak signal on a North American "
          "résumé and a politically constrained employer here.",
      aliases=("Noah's Ark Lab",), tags=("ai", "toronto", "china")),
    C("xanadu", "Xanadu", ca=2, us=1, cn=0, depth=1, role=1, domain=1, founder=1,
      prog=2, tech=2,
      why="Toronto quantum-computing company with a genuine research brand and "
          "little overlap with the analyst and product path he is on.",
      tags=("ai", "toronto", "research")),
    C("cyclica", "Cyclica", ca=1, us=0, cn=0, depth=1, role=1, domain=3,
      founder=2, prog=1, tech=2,
      why="Toronto computational drug-discovery company; strong overlap with his "
          "health-data interest, at a small scale.",
      tags=("ai", "toronto", "health")),
]

# =========================================================================
# Canadian fintech — his second-strongest domain, and where Shell reads well.
# =========================================================================
_FINTECH: list[CompanyProfile] = [
    C("interac", "Interac", ca=3, us=0, cn=0, depth=2, role=2, domain=3,
      founder=1, prog=2, tech=2,
      why="Operates Canada's payment rails. An unglamorous brand abroad, but "
          "national-scale data work in Toronto with a real student intake.",
      tags=("fintech", "toronto")),
    C("neofinancial", "Neo Financial", ca=2, us=0, cn=0, depth=2, role=3,
      domain=3, founder=3, prog=2, tech=2,
      why="Fast-growing Canadian challenger bank hiring analysts at co-op level, "
          "and small enough that a co-op sees product decisions end to end.",
      tags=("fintech", "canada")),
    C("koho", "KOHO", ca=2, us=0, cn=0, depth=2, role=2, domain=3, founder=2,
      prog=1,
      why="Toronto challenger-bank fintech with genuine product-analytics work "
          "and a reachable hiring bar.",
      tags=("fintech", "toronto")),
    C("float", "Float", ca=1, us=0, cn=0, depth=1, role=2, domain=3, founder=3,
      prog=1, tech=2,
      why="Toronto business-spend fintech; small, fast, and the kind of place "
          "where a co-op sits beside the people selling the product.",
      tags=("fintech", "toronto")),
    C("questrade", "Questrade", ca=3, us=0, cn=1, depth=2, role=3, domain=3,
      founder=1, prog=2, tech=2,
      why="Well-known Canadian brokerage with a substantial Toronto technology "
          "organisation and steady analyst hiring.",
      tags=("fintech", "toronto")),
    C("nuvei", "Nuvei", ca=2, us=1, cn=0, depth=2, role=2, domain=3, founder=1,
      prog=1, tech=2,
      why="Montreal payments company at real scale: solid fintech data work with "
          "a brand that carries little weight outside the industry.",
      tags=("fintech", "canada")),
    C("borrowell", "Borrowell", ca=1, us=0, cn=0, depth=1, role=2, domain=3,
      founder=2, prog=1,
      why="Toronto consumer-credit fintech with a small, accessible data team "
          "and a product surface a co-op can actually influence.",
      tags=("fintech", "toronto")),
    C("wave", "Wave Financial", ca=1, us=1, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=2, tech=2,
      why="Toronto SMB-accounting fintech with a long-running co-op programme.",
      tags=("fintech", "toronto")),
    C("clearco", "Clearco", ca=1, us=1, cn=0, depth=1, role=2, domain=3,
      founder=2, prog=1,
      why="Toronto fintech, much smaller than at its peak; local access is real "
          "but stability is not assured.",
      tags=("fintech", "toronto")),
    C("tmx", "TMX Group", ca=2, us=0, cn=0, depth=2, role=2, domain=3, founder=1,
      prog=2, tech=2,
      why="Toronto exchange operator with a genuine market-data platform and a "
          "structured student intake.",
      tags=("fintech", "toronto")),
    C("shakepay", "Shakepay", ca=1, us=0, cn=0, depth=1, role=1, domain=2,
      founder=2, prog=0,
      why="Canadian crypto fintech with a small engineering team; sector "
          "volatility makes it a higher-risk platform.",
      tags=("fintech", "canada")),
    C("stripe", "Stripe", ca=2, us=3, cn=1, depth=2, role=2, domain=3, founder=2,
      prog=3, tech=3,
      why="Named in his Tier 2. An elite engineering brand with a real Toronto "
          "office and one of the strongest signals a résumé can carry.",
      boards=(("greenhouse", "stripe"),), tags=("fintech", "toronto", "tier2")),
    C("plaid", "Plaid", ca=1, us=2, cn=0, depth=1, role=2, domain=3, founder=2,
      prog=2, tech=3,
      why="Fintech data infrastructure with a strong developer brand; Canadian "
          "hiring is opportunistic rather than programmatic.",
      boards=(("greenhouse", "plaid"),), tags=("fintech",)),
]

# =========================================================================
# Canadian banks, insurers and pensions — highest interview probability.
# `role_floor` stops the brand from lifting a pure reporting seat, which is
# the exact trap his own analysis told him to avoid.
# =========================================================================
_FINANCE: list[CompanyProfile] = [
    C("td", "TD Bank", ca=3, us=2, cn=1, depth=3, role=3, domain=2, founder=1,
      prog=3, tech=2,
      why="Very large Toronto technology and data organisation with a "
          "well-established co-op pipeline, and Layer 6 sits inside it.",
      boards=(("workday", "td"),), role_floor=True, tags=("bank", "toronto")),
    C("bmo", "BMO", ca=3, us=2, cn=1, depth=3, role=3, domain=2, founder=1,
      prog=3,
      why="Large Toronto data and analytics organisation running Fall co-op "
          "cohorts; named in his safety-net tier.",
      boards=(("workday", "bmo"),), role_floor=True, tags=("bank", "toronto")),
    C("cibc", "CIBC", ca=3, us=1, cn=1, depth=3, role=3, domain=2, founder=1,
      prog=3,
      why="The largest Canadian-posting employer seen in the board sweep; "
          "student hiring is strongly seasonal with a September window.",
      boards=(("workday", "cibc"),), role_floor=True, tags=("bank", "toronto")),
    C("manulife", "Manulife", ca=3, us=1, cn=3, depth=3, role=3, domain=2,
      founder=1, prog=3,
      why="Large Toronto data and AI organisation currently running an AI "
          "Enablement co-op. Its China business is major, so the name carries "
          "real weight if he ever moves back.",
      boards=(("workday", "manulife"),), role_floor=True,
      aliases=("宏利",), tags=("insurer", "toronto", "china")),
    C("sunlife", "Sun Life", ca=3, us=1, cn=3, depth=3, role=3, domain=2,
      founder=1, prog=3,
      why="Substantial Toronto technology and data organisation, named in his "
          "safety tier, and a strong brand in China.",
      boards=(("workday", "sunlife"),), role_floor=True,
      aliases=("永明",), tags=("insurer", "toronto", "china")),
    C("cppinvestments", "CPP Investments", ca=2, us=1, cn=1, depth=2, role=3,
      domain=3, founder=1, prog=3,
      why="Large Toronto institutional investor with a real technology and data "
          "group and a formal, published student programme.",
      role_floor=True, tags=("pension", "toronto")),
    C("otpp", "Ontario Teachers' Pension Plan", ca=2, us=1, cn=0, depth=2,
      role=3, domain=3, founder=1, prog=3,
      why="Toronto pension fund with a strong technology and data group and a "
          "well-run early-talent intake.",
      role_floor=True, tags=("pension", "toronto")),
    C("omers", "OMERS", ca=2, us=0, cn=0, depth=2, role=3, domain=3, founder=1,
      prog=3,
      why="Toronto pension fund running formal early-talent programmes with "
          "genuine analytics work behind them.",
      role_floor=True, tags=("pension", "toronto")),
    C("hoopp", "HOOPP", ca=1, us=0, cn=0, depth=2, role=3, domain=3, founder=1,
      prog=2,
      why="Toronto pension fund with fixed student hiring windows and a data "
          "team small enough to be visible inside.",
      role_floor=True, tags=("pension", "toronto")),
    C("nationalbank", "National Bank of Canada", ca=2, us=0, cn=0, depth=2,
      role=2, domain=2, founder=1, prog=2,
      why="Montreal bank with a growing technology arm, where most roles favour "
          "French speakers.",
      role_floor=True, tags=("bank", "canada")),
    C("intact", "Intact Financial", ca=2, us=0, cn=0, depth=2, role=3, domain=2,
      founder=1, prog=2,
      why="Canada's largest P&C insurer with a real data-science group — and his "
          "insurance-pricing GLM project reads directly onto it.",
      role_floor=True, tags=("insurer", "toronto")),
    C("definity", "Definity", ca=1, us=0, cn=0, depth=2, role=3, domain=2,
      founder=1, prog=2,
      why="Canadian insurer with an actuarial and data-science intake that "
          "matches his frequency-severity modelling work.",
      role_floor=True, tags=("insurer", "toronto")),
    C("fidelity", "Fidelity Canada", ca=2, us=2, cn=2, depth=2, role=3, domain=3,
      founder=1, prog=2,
      why="He already interned at Fidelity, so this is a warm re-entry rather "
          "than a cold application — which matters more than the tier given "
          "that his bottleneck is getting interviews at all.",
      override_personal="A",
      reason="An existing relationship is worth more than any brand delta when "
             "the failure mode is never reaching a human.",
      role_floor=True, tags=("fintech", "toronto", "warm")),
]

# =========================================================================
# Canadian ToB SaaS — reachable, and a co-op sees a real sales cycle.
# =========================================================================
_SAAS: list[CompanyProfile] = [
    C("stackadapt", "StackAdapt", ca=2, us=1, cn=0, depth=3, role=3, domain=3,
      founder=2, prog=2, tech=2,
      why="Toronto adtech with heavy data engineering, strong local hiring and "
          "an unusually high co-op conversion rate.",
      boards=(("greenhouse", "stackadapt"),), tags=("saas", "toronto", "data")),
    C("1password", "1Password", ca=3, us=2, cn=0, depth=3, role=2, domain=2,
      founder=2, prog=2, tech=3,
      why="Toronto security company with a genuine engineering brand in Canada "
          "and a product people actually recognise.",
      boards=(("ashby", "1password"),), tags=("saas", "toronto")),
    C("clio", "Clio", ca=2, us=1, cn=0, depth=3, role=3, domain=3, founder=2,
      prog=3, tech=2,
      why="One of Canada's largest private software companies, with a mature "
          "co-op pipeline and clean vertical-SaaS economics to learn from.",
      tags=("saas", "canada", "tob")),
    C("jobber", "Jobber", ca=2, us=1, cn=0, depth=2, role=3, domain=3, founder=3,
      prog=2, tech=2,
      why="Canadian vertical SaaS for home services: a textbook ToB motion at a "
          "size where a co-op can see the whole funnel.",
      boards=(("ashby", "jobber"),), tags=("saas", "canada", "tob")),
    C("kinaxis", "Kinaxis", ca=2, us=1, cn=1, depth=3, role=3, domain=3,
      founder=1, prog=3, tech=2,
      why="Ottawa supply-chain software with one of the strongest co-op "
          "programmes in Canada and real optimisation work.",
      tags=("saas", "canada", "tob")),
    C("coveo", "Coveo", ca=2, us=1, cn=0, depth=2, role=2, domain=3, founder=1,
      prog=3, tech=2,
      why="Quebec search and AI company with genuine applied-ML work and a "
          "long-running accredited co-op programme.",
      tags=("saas", "canada", "ai")),
    C("d2l", "D2L", ca=2, us=1, cn=0, depth=2, role=3, domain=2, founder=1,
      prog=3,
      why="Waterloo edtech with steady, predictable co-op hiring — a high "
          "interview-probability target.",
      boards=(("greenhouse", "d2l"),), tags=("saas", "canada")),
    C("docebo", "Docebo", ca=1, us=1, cn=0, depth=2, role=2, domain=2, founder=2,
      prog=2,
      why="Toronto SaaS with local engineering and analyst roles: commutable and "
          "realistic, with modest brand leverage.",
      boards=(("greenhouse", "docebo"),), tags=("saas", "toronto")),
    C("loopio", "Loopio", ca=1, us=0, cn=0, depth=2, role=2, domain=3, founder=3,
      prog=2,
      why="Toronto SaaS built around the RFP process, so a co-op is exposed to "
          "enterprise sales mechanics by the nature of the product.",
      tags=("saas", "toronto", "tob")),
    C("vena", "Vena Solutions", ca=1, us=1, cn=0, depth=2, role=3, domain=3,
      founder=2, prog=2,
      why="Toronto financial-planning SaaS: analyst-shaped work with real "
          "enterprise customers.",
      tags=("saas", "toronto", "tob")),
    C("q4", "Q4 Inc.", ca=1, us=1, cn=0, depth=2, role=2, domain=3, founder=2,
      prog=2,
      why="Toronto capital-markets SaaS combining his fintech and ToB interests "
          "at an accessible hiring bar.",
      tags=("saas", "toronto", "fintech")),
    C("dayforce", "Dayforce", ca=2, us=2, cn=0, depth=3, role=3, domain=2,
      founder=1, prog=3, tech=2,
      why="Large Toronto-area HR software employer with a substantial and "
          "predictable co-op intake.",
      aliases=("Ceridian",), tags=("saas", "toronto")),
    C("constellation", "Constellation Software", ca=2, us=1, cn=0, depth=3,
      role=2, domain=2, founder=2, prog=1, tech=2,
      why="Toronto serial acquirer of vertical software; unusual exposure to how "
          "many small ToB businesses really operate, but a fragmented employee "
          "experience across its operating groups.",
      tags=("saas", "toronto")),
    C("achievers", "Achievers", ca=1, us=1, cn=0, depth=2, role=2, domain=2,
      founder=2, prog=2,
      why="Toronto SaaS with local analyst roles: a realistic commutable option "
          "with limited résumé leverage.",
      boards=(("lever", "achievers"),), tags=("saas", "toronto")),
    C("geotab", "Geotab", ca=2, us=1, cn=0, depth=3, role=3, domain=3, founder=1,
      prog=3, tech=2,
      why="Oakville telematics company doing genuine large-scale data "
          "engineering, with one of the larger GTA co-op intakes.",
      boards=(("greenhouse", "geotab"),), tags=("saas", "toronto", "data")),
    C("magnetforensics", "Magnet Forensics", ca=1, us=1, cn=0, depth=2, role=2,
      domain=2, founder=1, prog=3, tech=2,
      why="Waterloo digital-forensics software with a reliable, repeating co-op "
          "programme.",
      tags=("saas", "canada")),
    C("axonify", "Axonify", ca=1, us=1, cn=0, depth=2, role=2, domain=2,
      founder=2, prog=2,
      why="Waterloo learning-platform SaaS with steady student hiring.",
      tags=("saas", "canada")),
    C("applyboard", "ApplyBoard", ca=2, us=0, cn=2, depth=2, role=3, domain=3,
      founder=2, prog=2, tech=2,
      why="Waterloo edtech marketplace whose core market is Chinese and South "
          "Asian students — a domain he understands from the inside, with real "
          "analyst roles attached.",
      tags=("saas", "canada", "china")),
    C("trulioo", "Trulioo", ca=1, us=1, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=2, tech=2,
      why="Vancouver identity-verification platform: regtech data work with "
          "enterprise customers.",
      boards=(("ashby", "trulioo"),), tags=("saas", "canada", "fintech")),
    C("opentext", "OpenText", ca=2, us=1, cn=1, depth=3, role=3, domain=2,
      founder=1, prog=3, tech=2,
      why="Large Waterloo enterprise-software employer with a big, predictable "
          "co-op intake, though the work is rarely distinctive.",
      tags=("saas", "canada")),
    C("faire", "Faire", ca=1, us=2, cn=0, depth=2, role=2, domain=3, founder=2,
      prog=2, tech=2,
      why="Wholesale marketplace with a substantial Toronto engineering office "
          "and strong data work on a competitive bar.",
      boards=(("greenhouse", "faire"),), tags=("saas", "toronto")),
    C("ecobee", "ecobee", ca=2, us=1, cn=0, depth=2, role=2, domain=2, founder=1,
      prog=3, tech=2,
      why="Toronto smart-home company with a recognised Canadian consumer brand "
          "and an established co-op programme.",
      tags=("saas", "toronto")),
    C("vidyard", "Vidyard", ca=1, us=1, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=2, tech=2,
      why="Waterloo video-for-sales SaaS, where a co-op sits close to the "
          "revenue motion by the nature of the product.",
      tags=("saas", "canada", "tob")),
    C("lightspeed", "Lightspeed", ca=2, us=1, cn=0, depth=3, role=3, domain=3,
      founder=2, prog=3, tech=2,
      why="Montreal commerce platform, one of Canada's larger public software "
          "companies, with recurring student hiring and real analyst seats.",
      tags=("saas", "canada", "commerce")),
]

# =========================================================================
# Global technology employers with genuine Canadian hiring.
# =========================================================================
_GLOBAL: list[CompanyProfile] = [
    C("amazon", "Amazon", ca=3, us=3, cn=3, depth=3, role=3, domain=2, founder=1,
      prog=3, tech=3,
      why="The largest structured student pipeline in technology, with real "
          "Canadian co-op cohorts including Toronto. Strong brand in all three "
          "markets he cares about and a genuinely reachable application route.",
      tags=("bigtech", "toronto")),
    C("google", "Google", ca=3, us=3, cn=3, depth=3, role=2, domain=2, founder=1,
      prog=3, tech=3,
      why="Global engineering benchmark with a large Waterloo and Toronto "
          "presence and a mature student programme; the bar is the constraint, "
          "not the access.",
      tags=("bigtech", "toronto")),
    C("microsoft", "Microsoft", ca=3, us=3, cn=3, depth=3, role=3, domain=2,
      founder=1, prog=3, tech=3,
      why="Strong platform with an established Canadian engineering presence, a "
          "well-run early-careers programme and genuine product-analyst tracks.",
      tags=("bigtech", "canada")),
    C("nvidia", "NVIDIA", ca=2, us=3, cn=3, depth=2, role=1, domain=2, founder=1,
      prog=3, tech=3,
      why="Defining compute platform of the AI era, with a Toronto-area "
          "presence; roles skew deeply technical relative to his strengths.",
      tags=("bigtech", "ai")),
    C("openai", "OpenAI", ca=3, us=3, cn=3, depth=0, role=1, domain=3, founder=2,
      prog=1, tech=3,
      why="The strongest résumé signal in the field. Kept in the registry on "
          "brand alone — Canadian access is effectively nil, which is recorded "
          "as an access status rather than as a lower tier.",
      boards=(("ashby", "openai"),), tags=("ai", "us")),
    C("anthropic", "Anthropic", ca=3, us=3, cn=2, depth=0, role=1, domain=3,
      founder=2, prog=2, tech=3,
      why="Frontier AI lab with an exceptional engineering reputation and a "
          "published internship; the same Canadian access caveat as OpenAI.",
      boards=(("greenhouse", "anthropic"),), tags=("ai", "us")),
    C("ibm", "IBM", ca=2, us=2, cn=2, depth=3, role=3, domain=2, founder=1,
      prog=3, tech=2,
      why="Named in his notes as a route into enterprise AI solutions work — the "
          "specific gap he identified. Long-standing Canadian footprint and a "
          "large, accessible student intake.",
      tags=("enterprise", "toronto", "ai")),
    C("thomsonreuters", "Thomson Reuters", ca=3, us=2, cn=1, depth=3, role=3,
      domain=3, founder=1, prog=3, tech=2,
      why="Toronto Labs does genuine applied AI on legal and financial data, "
          "with campus and technology internships. An unusually good fit for a "
          "CS+DS student who wants domain-heavy ML.",
      aliases=("Thomson", "Reuters"), tags=("canada", "toronto", "ai")),
    C("autodesk", "Autodesk", ca=2, us=2, cn=2, depth=2, role=2, domain=2,
      founder=1, prog=3, tech=2,
      why="Strong engineering culture with an official, well-published student "
          "programme and a Toronto presence.",
      tags=("saas", "toronto")),
    C("intuit", "Intuit", ca=2, us=3, cn=0, depth=2, role=3, domain=3, founder=1,
      prog=3, tech=2,
      why="Toronto office with an explicit Fall software co-op stream, and a "
          "fintech product surface that matches his interests.",
      tags=("fintech", "toronto")),
    C("amd", "AMD", ca=2, us=3, cn=3, depth=3, role=1, domain=1, founder=1,
      prog=3, tech=2,
      why="Large Markham engineering site running real Fall co-op cohorts. "
          "Strong brand, but the work is firmware and silicon rather than "
          "anything on his analyst or product path.",
      tags=("hardware", "toronto")),
    C("uber", "Uber", ca=2, us=3, cn=2, depth=2, role=2, domain=3, founder=2,
      prog=3, tech=3,
      why="Large-scale marketplace data work with a real Toronto engineering "
          "site and a structured internship.",
      tags=("bigtech", "toronto")),
    C("instacart", "Instacart", ca=1, us=2, cn=0, depth=2, role=3, domain=3,
      founder=2, prog=2, tech=2,
      why="Toronto data and analytics roles on a marketplace with genuinely "
          "interesting demand modelling.",
      boards=(("greenhouse", "instacart"),), tags=("toronto", "data")),
    C("databricks", "Databricks", ca=1, us=3, cn=2, depth=1, role=2, domain=3,
      founder=2, prog=3, tech=3,
      why="Leading data and AI platform, directly relevant to a data-engineering "
          "trajectory, though Canadian hiring is limited.",
      boards=(("greenhouse", "databricks"),), tags=("data",)),
    C("snowflake", "Snowflake", ca=1, us=3, cn=1, depth=1, role=2, domain=3,
      founder=2, prog=3, tech=3,
      why="Major data platform and a strong signal for data work, though its "
          "Canadian presence is thin.",
      boards=(("ashby", "snowflake"),), tags=("data",)),
    C("mongodb", "MongoDB", ca=1, us=2, cn=1, depth=2, role=2, domain=3,
      founder=1, prog=3, tech=3,
      why="Database platform with a real Canadian presence and a published "
          "internship programme.",
      boards=(("greenhouse", "mongodb"),), tags=("data",)),
    C("datadog", "Datadog", ca=1, us=2, cn=0, depth=2, role=2, domain=3,
      founder=1, prog=3, tech=3,
      why="Large-scale observability platform with serious distributed-systems "
          "work and a growing Canadian office.",
      boards=(("greenhouse", "datadog"),), tags=("data",)),
    C("cloudflare", "Cloudflare", ca=1, us=2, cn=1, depth=1, role=1, domain=2,
      founder=1, prog=3, tech=3,
      why="Core internet infrastructure with an excellent systems signal, but "
          "the work sits further from his analyst strengths.",
      boards=(("greenhouse", "cloudflare"),), tags=("infra",)),
    C("figma", "Figma", ca=2, us=3, cn=2, depth=1, role=2, domain=2, founder=2,
      prog=3, tech=3,
      why="Elite product brand and a tool he already uses; a strong signal for "
          "the product-analyst direction, with limited Canadian hiring.",
      boards=(("greenhouse", "figma"),), tags=("product",)),
    C("notion", "Notion", ca=2, us=2, cn=2, depth=1, role=2, domain=2, founder=2,
      prog=2, tech=3,
      why="Strong product brand with real recognition in China; a small team "
          "and little Canadian hiring.",
      boards=(("ashby", "notion"),), tags=("product",)),
    C("duolingo", "Duolingo", ca=2, us=3, cn=2, depth=1, role=2, domain=3,
      founder=2, prog=3, tech=3,
      why="Genuine applied-ML product work behind a consumer surface, and a "
          "famously competitive, well-published internship.",
      tags=("product", "ai")),
    C("coinbase", "Coinbase", ca=1, us=2, cn=1, depth=1, role=2, domain=3,
      founder=1, prog=2, tech=2,
      why="Major fintech engineering brand, but hiring rises and falls with the "
          "crypto cycle and Canadian roles are sparse.",
      boards=(("greenhouse", "coinbase"),), tags=("fintech",)),
]

# =========================================================================
# Global financial employers with large Toronto analytics organisations.
# These were a serious omission: they run some of the biggest analyst intakes
# in the city, which is precisely his highest-probability role family.
# =========================================================================
_FINANCE_GLOBAL: list[CompanyProfile] = [
    C("capitalone", "Capital One Canada", ca=2, us=3, cn=0, depth=3, role=3,
      domain=3, founder=1, prog=3, tech=2,
      why="Toronto analytics organisation built around credit modelling, with "
          "one of the strongest data-analyst intakes in the city. Its whole "
          "culture is analyst-first, which is exactly his top role family.",
      role_floor=True, tags=("fintech", "toronto")),
    C("amex", "American Express Canada", ca=2, us=3, cn=1, depth=2, role=3,
      domain=3, founder=1, prog=3,
      why="Toronto analytics and risk-modelling teams with a formal student "
          "intake and a brand that reads clearly on a finance-data résumé.",
      aliases=("American Express",), role_floor=True, tags=("fintech", "toronto")),
    C("mastercard", "Mastercard", ca=2, us=3, cn=1, depth=2, role=3, domain=3,
      founder=1, prog=3, tech=2,
      why="Toronto and Vancouver data and AI teams working on payments "
          "intelligence; strong brand plus genuine modelling work.",
      role_floor=True, tags=("fintech", "toronto")),
    C("visa", "Visa Canada", ca=2, us=3, cn=2, depth=2, role=2, domain=3,
      founder=1, prog=3,
      why="Global payments infrastructure with Toronto roles. The brand should "
          "lift only its technical and data streams, never a general seat.",
      boards=(("smartrecruiters", "Visa"),), role_floor=True,
      tags=("fintech", "toronto")),
    C("eqbank", "EQ Bank", ca=2, us=0, cn=0, depth=2, role=3, domain=3,
      founder=2, prog=2, tech=2,
      why="Canada's largest digital-only bank; small enough that a co-op sees "
          "product decisions, large enough to have a real data organisation.",
      aliases=("Equitable Bank",), tags=("fintech", "toronto")),
    C("imco", "IMCO", ca=1, us=0, cn=0, depth=2, role=3, domain=3, founder=1,
      prog=2,
      why="Toronto institutional investment manager with a growing technology "
          "and data group and a small, visible student intake.",
      role_floor=True, tags=("pension", "toronto")),
    C("cdpq", "CDPQ", ca=2, us=0, cn=0, depth=2, role=2, domain=3, founder=1,
      prog=2,
      why="Quebec's institutional investor with a real data organisation; most "
          "roles favour French speakers.",
      role_floor=True, tags=("pension", "canada")),
    C("aviva", "Aviva Canada", ca=2, us=0, cn=0, depth=2, role=3, domain=2,
      founder=1, prog=2,
      why="Toronto insurer with a data-science team where his frequency-severity "
          "pricing project is directly relevant experience.",
      role_floor=True, tags=("insurer", "toronto")),
    C("canadalife", "Canada Life", ca=2, us=0, cn=1, depth=2, role=3, domain=2,
      founder=1, prog=3,
      why="Large Canadian insurer with a predictable co-op intake across "
          "Toronto and London, Ontario.",
      role_floor=True, tags=("insurer", "canada")),
    C("meridian", "Meridian Credit Union", ca=1, us=0, cn=0, depth=2, role=3,
      domain=2, founder=1, prog=2,
      why="Ontario's largest credit union, headquartered in the GTA, with a "
          "modest but genuine analytics function and a reachable hiring bar.",
      role_floor=True, safety_net=True, tags=("bank", "toronto")),
]

# =========================================================================
# Health data institutions and research hospitals. Several of these are not
# safety nets at all — ICES and CIHI are among the best domain matches he has.
# =========================================================================
_HEALTH_DATA: list[CompanyProfile] = [
    C("ices", "ICES", ca=1, us=0, cn=0, depth=2, role=3, domain=3, founder=1,
      prog=2, tech=2,
      why="Ontario's health-data research institute, holding the province's "
          "linked administrative health records. For a CS+DS student doing "
          "diagnostic-pathway research this is close to a perfect domain match, "
          "whatever its brand looks like from outside healthcare.",
      override_personal="B",
      reason="The score is right that ICES has almost no public brand and no "
             "founder capital, and those two drag it to C. But access to "
             "Ontario's linked health records is the single scarcest asset for "
             "the clinical-AI direction he has actually committed to, and no "
             "input in the model represents data access at all.",
      tags=("health", "toronto", "research", "data")),
    C("cihi", "Canadian Institute for Health Information", ca=1, us=0, cn=0,
      depth=2, role=3, domain=3, founder=1, prog=2,
      why="National health-data agency in Toronto and Ottawa with real "
          "analyst roles and a structured student intake.",
      aliases=("CIHI",), tags=("health", "toronto", "data")),
    C("ontariohealth", "Ontario Health", ca=2, us=0, cn=0, depth=2, role=3,
      domain=3, founder=1, prog=2,
      why="Provincial digital-health agency running large clinical data "
          "platforms; slow-moving, but the domain exposure is real.",
      safety_net=True, tags=("health", "toronto", "government")),
    C("camh", "CAMH", ca=2, us=0, cn=0, depth=2, role=2, domain=3, founder=1,
      prog=2,
      why="Toronto mental-health hospital and research institute with genuine "
          "clinical-data and research-analyst roles.",
      tags=("health", "toronto", "research")),
    C("sunnybrook", "Sunnybrook Research Institute", ca=2, us=0, cn=0, depth=2,
      role=2, domain=3, founder=1, prog=2,
      why="Major Toronto hospital research institute with imaging and clinical "
          "AI groups he could realistically join as a student.",
      tags=("health", "toronto", "research")),
    C("unityhealth", "Unity Health Toronto", ca=2, us=0, cn=0, depth=2, role=2,
      domain=3, founder=2, prog=2, tech=2,
      why="Runs one of Canada's most advanced hospital data-science teams and "
          "has deployed its own clinical prediction models in production — "
          "unusually close to what his Remeda project is trying to be.",
      tags=("health", "toronto", "research", "ai")),
    C("talai", "Tali AI", ca=1, us=0, cn=0, depth=1, role=2, domain=3, founder=3,
      prog=1, tech=2,
      why="Toronto clinical-AI scribe company. Small, LLM-native, and selling "
          "directly to clinicians — a co-op here sees the whole buyer loop.",
      tags=("health", "toronto", "ai")),
    C("seamlessmd", "SeamlessMD", ca=1, us=1, cn=0, depth=1, role=2, domain=3,
      founder=3, prog=1,
      why="Toronto patient-engagement platform selling into hospital systems; "
          "exactly the procurement vantage point his notes ask for.",
      tags=("health", "toronto", "tob")),
    C("swiftmedical", "Swift Medical", ca=1, us=1, cn=0, depth=1, role=2,
      domain=3, founder=2, prog=1, tech=2,
      why="Toronto wound-care imaging AI with real computer-vision work at a "
          "small, accessible scale.",
      tags=("health", "toronto", "ai")),
    C("hypercare", "Hypercare", ca=1, us=0, cn=0, depth=1, role=2, domain=3,
      founder=3, prog=1,
      why="Toronto clinical-communication startup founded out of UofT; small "
          "team, direct hospital customers.",
      tags=("health", "toronto")),
    C("janeapp", "Jane App", ca=2, us=1, cn=0, depth=2, role=3, domain=3,
      founder=2, prog=2, tech=2,
      why="Vancouver practice-management software with an unusually strong "
          "engineering culture for health SaaS and open remote-in-Canada hiring.",
      tags=("health", "canada", "tob")),
    C("fullscript", "Fullscript", ca=1, us=1, cn=0, depth=2, role=3, domain=3,
      founder=2, prog=2, tech=2,
      why="Ottawa health-commerce platform with a real data team and steady "
          "student hiring.",
      tags=("health", "canada")),
]

# =========================================================================
# Research institutes and accelerators. Their value to him is network access
# and interview reachability, which is his actual bottleneck.
# =========================================================================
_RESEARCH: list[CompanyProfile] = [
    C("mila", "Mila", ca=2, us=1, cn=1, depth=2, role=2, domain=3, founder=2,
      prog=3, tech=3,
      why="Quebec AI institute and one of the two most credible AI research "
          "brands in Canada; publishes internships and hosts industry partners.",
      tags=("ai", "canada", "research")),
    C("amii", "Amii", ca=1, us=0, cn=0, depth=1, role=2, domain=3, founder=2,
      prog=2, tech=2,
      why="Alberta machine-intelligence institute with applied-AI residencies "
          "and industry placements.",
      tags=("ai", "canada", "research")),
    C("cdl", "Creative Destruction Lab", ca=2, us=1, cn=0, depth=1, role=2,
      domain=3, founder=3, prog=2,
      why="He is already applying to CDL Health, so this is an existing thread "
          "rather than a cold start. Its value is founder network access, not "
          "the job itself.",
      tags=("toronto", "network", "warm")),
    C("marsdd", "MaRS Discovery District", ca=2, us=0, cn=0, depth=1, role=2,
      domain=3, founder=3, prog=2,
      why="The centre of Toronto's health and climate innovation network. Small "
          "employer, but its network value substantially exceeds its headcount.",
      boards=(("bamboohr", "marsdd"),), tags=("toronto", "network", "health")),
]

# =========================================================================
# Enterprise technology employers with large, predictable Canadian co-op
# programmes. Unglamorous, but they answer his actual bottleneck.
# =========================================================================
_ENTERPRISE: list[CompanyProfile] = [
    C("sap", "SAP Canada", ca=2, us=2, cn=2, depth=3, role=3, domain=3,
      founder=1, prog=3, tech=2,
      why="One of the largest and most reliable co-op programmes in Canada, "
          "across Waterloo and Vancouver, on genuine enterprise data products.",
      tags=("enterprise", "canada")),
    C("adobe", "Adobe Canada", ca=2, us=3, cn=2, depth=2, role=2, domain=2,
      founder=1, prog=3, tech=2,
      why="Ottawa and Toronto engineering with a well-run internship and a "
          "brand that carries in all three of his markets.",
      tags=("enterprise", "canada")),
    C("salesforce", "Salesforce Canada", ca=2, us=3, cn=1, depth=2, role=3,
      domain=3, founder=2, prog=3,
      why="Toronto and Vancouver offices, and the canonical enterprise SaaS "
          "sales motion to learn from at close range.",
      tags=("enterprise", "canada", "tob")),
    C("blackberry", "BlackBerry", ca=3, us=1, cn=2, depth=3, role=2, domain=2,
      founder=1, prog=3, tech=2,
      why="Waterloo security and automotive software with one of the longest "
          "running co-op pipelines in Canada. The consumer brand is history; "
          "the engineering organisation is not.",
      tags=("enterprise", "canada")),
    C("nokia", "Nokia Canada", ca=2, us=1, cn=2, depth=3, role=2, domain=2,
      founder=1, prog=3, tech=2,
      why="Large Ottawa R&D site with a substantial and predictable co-op "
          "intake in networking software.",
      tags=("enterprise", "canada")),
    C("ciena", "Ciena", ca=1, us=2, cn=1, depth=3, role=2, domain=2, founder=1,
      prog=3, tech=2,
      why="Ottawa optical-networking engineering with a reliable student "
          "programme; technically solid, domain-distant from his interests.",
      tags=("enterprise", "canada")),
    C("ericsson", "Ericsson Canada", ca=1, us=1, cn=2, depth=3, role=2,
      domain=2, founder=1, prog=3,
      why="Ottawa and Montreal R&D with a steady co-op intake.",
      tags=("enterprise", "canada")),
    C("genetec", "Genetec", ca=1, us=1, cn=0, depth=3, role=2, domain=2,
      founder=1, prog=3, tech=2,
      why="Montreal security-software company with a large, well-regarded "
          "internship programme.",
      tags=("enterprise", "canada")),
]

# =========================================================================
# Additional Canadian technology employers across Waterloo, Ottawa,
# Montreal and Vancouver.
# =========================================================================
_CANADA_TECH: list[CompanyProfile] = [
    C("descartes", "Descartes Systems", ca=1, us=1, cn=0, depth=3, role=3,
      domain=3, founder=1, prog=3, tech=2,
      why="Waterloo logistics SaaS at real scale, with steady co-op hiring and "
          "genuine supply-chain data work.",
      tags=("saas", "canada", "tob")),
    C("esentire", "eSentire", ca=1, us=1, cn=0, depth=2, role=2, domain=2,
      founder=2, prog=3, tech=2,
      why="Waterloo managed cybersecurity with a real detection-engineering "
          "practice and a reliable student intake.",
      tags=("saas", "canada")),
    C("auvik", "Auvik Networks", ca=1, us=1, cn=0, depth=2, role=2, domain=2,
      founder=2, prog=2, tech=2,
      why="Waterloo network-monitoring SaaS; small, technical, and a realistic "
          "co-op target.",
      tags=("saas", "canada")),
    C("miovision", "Miovision", ca=1, us=1, cn=0, depth=2, role=3, domain=3,
      founder=2, prog=2, tech=2,
      why="Kitchener traffic-data company doing genuine computer vision and "
          "large-scale sensor analytics for municipal buyers.",
      tags=("saas", "canada", "data")),
    C("clearpath", "Clearpath Robotics / OTTO Motors", ca=1, us=1, cn=0,
      depth=2, role=1, domain=1, founder=2, prog=3, tech=2,
      why="Kitchener industrial robotics with a strong co-op programme; far "
          "from his analyst path but a well-regarded engineering employer.",
      tags=("canada", "hardware")),
    C("tophat", "Top Hat", ca=1, us=1, cn=0, depth=2, role=2, domain=2,
      founder=2, prog=2,
      why="Toronto edtech with local product and data roles at an accessible "
          "hiring bar.",
      tags=("saas", "toronto")),
    C("wattpad", "Wattpad", ca=2, us=1, cn=1, depth=2, role=3, domain=3,
      founder=2, prog=2, tech=2,
      why="Toronto consumer platform with a genuinely interesting "
          "recommendation and content-analytics problem at real scale.",
      tags=("saas", "toronto", "data")),
    C("bluecat", "BlueCat Networks", ca=1, us=1, cn=0, depth=2, role=2,
      domain=2, founder=1, prog=2, tech=2,
      why="Toronto network-infrastructure software; unglamorous, technically "
          "serious, and locally reachable.",
      tags=("saas", "toronto")),
    C("soti", "SOTI", ca=1, us=1, cn=0, depth=3, role=2, domain=2, founder=1,
      prog=3,
      why="Mississauga enterprise-mobility software with a large and "
          "predictable co-op intake.",
      tags=("saas", "toronto")),
    C("hopper", "Hopper", ca=2, us=2, cn=0, depth=3, role=3, domain=3,
      founder=2, prog=2, tech=2,
      why="Montreal travel-fintech company built on price-prediction models — "
          "one of the most data-heavy consumer products in Canada.",
      tags=("saas", "canada", "data")),
    C("ssense", "SSENSE", ca=2, us=1, cn=2, depth=3, role=3, domain=2,
      founder=2, prog=2, tech=2,
      why="Montreal commerce company with an unusually strong engineering and "
          "data organisation, and real recognition in China. Rated as a "
          "technology employer, not as retail.",
      tags=("saas", "canada", "commerce")),
    C("visier", "Visier", ca=1, us=1, cn=0, depth=2, role=3, domain=3,
      founder=2, prog=2, tech=2,
      why="Vancouver people-analytics platform: analyst-shaped product work "
          "with enterprise customers.",
      tags=("saas", "canada", "tob")),
    C("thinkific", "Thinkific", ca=1, us=1, cn=0, depth=2, role=2, domain=2,
      founder=2, prog=2,
      why="Vancouver SaaS in online education; small engineering team, modest "
          "brand, but genuine Canadian hiring.",
      tags=("saas", "canada")),
    C("hootsuite", "Hootsuite", ca=2, us=1, cn=0, depth=2, role=2, domain=2,
      founder=2, prog=2,
      why="Vancouver SaaS with a recognisable Canadian brand; solid "
          "engineering, though the company's growth has slowed.",
      boards=(("greenhouse", "hootsuite"),), tags=("saas", "canada")),
    C("absolute", "Absolute Security", ca=1, us=1, cn=0, depth=2, role=2,
      domain=2, founder=1, prog=2,
      why="Vancouver endpoint-security company with steady Canadian hiring.",
      tags=("saas", "canada")),
    C("copperleaf", "Copperleaf Technologies", ca=1, us=1, cn=0, depth=2,
      role=3, domain=3, founder=2, prog=2, tech=2,
      why="Vancouver decision-analytics software for asset-heavy industries — "
          "genuinely analyst-shaped work with enterprise buyers.",
      tags=("saas", "canada", "tob")),
    C("dapperlabs", "Dapper Labs", ca=1, us=1, cn=1, depth=2, role=2, domain=2,
      founder=2, prog=2, tech=2,
      why="Vancouver blockchain company with real engineering; sector risk is "
          "high and hiring has contracted.",
      tags=("saas", "canada")),
    C("klue", "Klue", ca=1, us=1, cn=0, depth=2, role=2, domain=3, founder=3,
      prog=2,
      why="Vancouver competitive-intelligence SaaS sold directly to sales "
          "teams, so a co-op is close to the revenue motion.",
      tags=("saas", "canada", "tob")),
    C("mindbridge", "MindBridge AI", ca=1, us=1, cn=0, depth=2, role=3,
      domain=3, founder=3, prog=2, tech=2,
      why="Ottawa AI for financial audit: applied ML on financial data with "
          "enterprise buyers — a tight three-way fit with his interests.",
      tags=("ai", "canada", "tob", "fintech")),
    C("loblawdigital", "Loblaw Digital", ca=2, us=0, cn=0, depth=3, role=3,
      domain=2, founder=1, prog=3, tech=2,
      why="Rated as a technology organisation rather than as retail: Toronto "
          "e-commerce engineering with a large, genuine co-op intake. The "
          "retail exclusion applies to store operations, not to this.",
      role_floor=True, tags=("commerce", "toronto")),
    C("cira", "CIRA", ca=1, us=0, cn=0, depth=1, role=2, domain=2, founder=1,
      prog=2,
      why="Ottawa internet registry with a small technical team and a genuinely "
          "public-interest mandate.",
      safety_net=True, tags=("canada",)),
]

# =========================================================================
# Public sector. Included on his instruction as a FLOOR only: high interview
# probability, low career leverage. `safety_net` keeps them from ever
# displacing a real target in the recommended set.
# =========================================================================
_PUBLIC: list[CompanyProfile] = [
    C("bankofcanada", "Bank of Canada", ca=3, us=0, cn=1, depth=2, role=3,
      domain=3, founder=1, prog=3, tech=2,
      why="The exception among public employers: genuine economic research and "
          "data work, a competitive published student programme, and a name "
          "that carries real weight in Canada.",
      tags=("government", "canada", "data")),
    C("statcan", "Statistics Canada", ca=3, us=0, cn=0, depth=3, role=3,
      domain=2, founder=1, prog=3,
      why="The largest statistical organisation in the country, with real "
          "methodology work and a large, published student intake. Slow, but "
          "a legitimate data-analyst credential.",
      safety_net=True, tags=("government", "canada", "data")),
    C("cityoftoronto", "City of Toronto", ca=2, us=0, cn=0, depth=2, role=3,
      domain=1, founder=1, prog=2,
      why="Floor option. Real municipal data work and a high interview "
          "probability, with little career leverage and no founding value.",
      boards=(("successfactors", "https://jobs.toronto.ca/jobsatcity"),),
      safety_net=True, role_floor=True, tags=("government", "toronto")),
    C("ops", "Ontario Public Service", ca=2, us=0, cn=0, depth=3, role=3,
      domain=1, founder=1, prog=3,
      why="Floor option with one of the largest student intakes in the "
          "province; reporting-shaped work but very reachable.",
      aliases=("OPS",), safety_net=True, role_floor=True,
      tags=("government", "toronto")),
    C("ontariodigital", "Ontario Digital Service", ca=1, us=0, cn=0, depth=1,
      role=2, domain=2, founder=2, prog=2, tech=2,
      why="The one part of the Ontario government doing recognisable modern "
          "product and service design work; a better floor than the rest.",
      safety_net=True, tags=("government", "toronto")),
    C("metrolinx", "Metrolinx", ca=2, us=0, cn=0, depth=2, role=3, domain=1,
      founder=1, prog=2,
      why="Floor option. Transit planning generates real operational data, but "
          "the work is reporting-shaped and the organisation moves slowly.",
      safety_net=True, role_floor=True, tags=("government", "toronto")),
    C("ttc", "Toronto Transit Commission", ca=2, us=0, cn=0, depth=1, role=2,
      domain=1, founder=1, prog=2,
      why="Floor option, listed for completeness: local, reachable, and of "
          "limited career value to him.",
      safety_net=True, role_floor=True, tags=("government", "toronto")),
    C("hydroone", "Hydro One", ca=2, us=0, cn=0, depth=2, role=2, domain=1,
      founder=1, prog=3,
      why="Floor option with a large, predictable student intake and grid data "
          "at real scale.",
      safety_net=True, role_floor=True, tags=("government", "toronto")),
    C("canadapost", "Canada Post", ca=3, us=0, cn=0, depth=2, role=2, domain=1,
      founder=1, prog=2,
      why="Floor option. Nationally recognised, with a real logistics data "
          "organisation and no career leverage for his direction.",
      safety_net=True, role_floor=True, tags=("government", "canada")),
]

# =========================================================================
# Investment, quant, asset management, capital markets. A direction the
# candidate named explicitly: data- and quant-heavy work he is well suited to,
# with real Toronto co-op intakes. role_floor: the brand must lift only the
# technical / quant / data seats, never a sales or relationship one.
# =========================================================================
_INVESTMENT: list[CompanyProfile] = [
    C("brookfield", "Brookfield", ca=3, us=2, cn=1, depth=2, role=2, domain=3,
      founder=1, prog=2, tech=1,
      why="One of the world's largest alternative asset managers, "
          "headquartered in Toronto, with a growing technology and data group "
          "across real assets and infrastructure.",
      role_floor=True, tags=("investment", "toronto")),
    C("onex", "Onex", ca=2, us=1, cn=0, depth=1, role=2, domain=3, founder=1,
      prog=2, tech=1,
      why="Major Toronto private-equity firm with a small but genuine "
          "data-and-analytics function supporting deal and portfolio work.",
      role_floor=True, tags=("investment", "toronto")),
    C("psp", "PSP Investments", ca=2, us=1, cn=0, depth=2, role=3, domain=3,
      founder=1, prog=2, tech=2,
      why="Large federal public-sector pension investor (Montreal/Ottawa) with "
          "a real quant, data and technology organisation and a formal intake.",
      aliases=("PSP",), role_floor=True, tags=("pension", "investment", "canada")),
    C("aimco", "AIMCo", ca=2, us=0, cn=0, depth=2, role=3, domain=3, founder=1,
      prog=2, tech=2,
      why="Alberta's institutional investor, building out quantitative and data "
          "teams with a defined early-talent programme.",
      role_floor=True, tags=("pension", "investment", "canada")),
    C("bci", "BCI", ca=1, us=0, cn=0, depth=2, role=3, domain=3, founder=1,
      prog=2, tech=2,
      why="British Columbia Investment Management — a large institutional "
          "investor in Victoria with genuine quant and technology roles.",
      role_floor=True, tags=("pension", "investment", "canada")),
    C("mackenzie", "Mackenzie Investments", ca=2, us=0, cn=0, depth=2, role=3,
      domain=3, founder=1, prog=2, tech=1,
      why="Toronto asset manager (IGM) with an investment-analytics and data "
          "group and a student intake.",
      role_floor=True, tags=("investment", "toronto")),
    C("fiera", "Fiera Capital", ca=1, us=1, cn=0, depth=2, role=2, domain=3,
      founder=1, prog=1, tech=1,
      why="One of Canada's largest independent asset managers (Montreal), with "
          "quantitative strategies and a data team.",
      role_floor=True, tags=("investment", "canada")),
    C("polarasset", "Polar Asset Management", ca=1, us=1, cn=0, depth=1, role=2,
      domain=3, founder=1, prog=1, tech=2,
      why="Toronto multi-strategy hedge fund with genuine quantitative and "
          "technology needs; small, so a role sits close to the strategy.",
      role_floor=True, tags=("investment", "toronto", "quant")),
    C("pictonmahoney", "Picton Mahoney", ca=1, us=0, cn=0, depth=1, role=2,
      domain=3, founder=1, prog=1, tech=1,
      why="Toronto alternative asset manager with quantitative and data-driven "
          "strategies.",
      role_floor=True, tags=("investment", "toronto", "quant")),
    C("tdsecurities", "TD Securities", ca=3, us=2, cn=1, depth=3, role=3,
      domain=3, founder=1, prog=3, tech=2,
      why="TD's capital-markets arm: real trading technology, quant and data "
          "engineering in Toronto, with a structured co-op pipeline.",
      role_floor=True, tags=("investment", "bank", "toronto", "quant")),
    C("rbccm", "RBC Capital Markets", ca=3, us=2, cn=1, depth=3, role=3,
      domain=3, founder=1, prog=3, tech=2,
      why="RBC's capital-markets arm with trading-technology and quant "
          "developer roles in Toronto and a mature student intake.",
      aliases=("RBC Capital Markets",), role_floor=True,
      tags=("investment", "bank", "toronto", "quant")),
    C("bmocm", "BMO Capital Markets", ca=2, us=2, cn=1, depth=2, role=3,
      domain=3, founder=1, prog=3, tech=2,
      why="BMO's capital-markets arm with trading-tech and quant roles and a "
          "co-op programme.",
      role_floor=True, tags=("investment", "bank", "toronto", "quant")),
    C("scotiagbm", "Scotiabank Global Banking & Markets", ca=2, us=1, cn=1,
      depth=2, role=3, domain=3, founder=1, prog=3, tech=2,
      why="Scotiabank's capital-markets arm; quant and trading-technology roles "
          "with a Velocity-linked student intake.",
      aliases=("Scotiabank GBM",), role_floor=True,
      tags=("investment", "bank", "toronto", "quant")),
    C("nbf", "National Bank Financial", ca=2, us=0, cn=0, depth=2, role=2,
      domain=3, founder=1, prog=2, tech=1,
      why="National Bank's capital-markets arm (Montreal) with trading and "
          "data roles; French an asset.",
      role_floor=True, tags=("investment", "bank", "canada")),
    C("bloomberg", "Bloomberg", ca=1, us=3, cn=2, depth=2, role=3, domain=3,
      founder=1, prog=3, tech=3,
      why="Financial-data and software giant. A serious engineering brand, real "
          "data and software roles, and a published internship reachable from "
          "Canada.",
      role_floor=True, tags=("investment", "data", "fintech")),
    C("morningstar", "Morningstar Canada", ca=1, us=2, cn=1, depth=2, role=3,
      domain=3, founder=1, prog=2, tech=2,
      why="Investment-data and research company with a Toronto office and real "
          "data-engineering and analyst roles.",
      role_floor=True, tags=("investment", "data", "toronto")),
    C("lseg", "LSEG (Refinitiv)", ca=2, us=2, cn=1, depth=3, role=3, domain=3,
      founder=1, prog=3, tech=2,
      why="London Stock Exchange Group's data arm (former Refinitiv, Thomson "
          "Reuters heritage) with a large Toronto technology and data centre.",
      aliases=("Refinitiv", "LSEG"), role_floor=True,
      tags=("investment", "data", "toronto", "fintech")),
]

# =========================================================================
# More global technology employers with genuine Canadian data/AI/SWE hiring.
# =========================================================================
_GLOBAL_TECH_2: list[CompanyProfile] = [
    C("spotify", "Spotify", ca=2, us=3, cn=2, depth=2, role=2, domain=3,
      founder=2, prog=3, tech=3,
      why="Large consumer-ML and data brand with a real Toronto engineering "
          "presence and a competitive, published internship.",
      tags=("bigtech", "toronto", "data")),
    C("tiktok", "TikTok", ca=2, us=3, cn=3, depth=2, role=2, domain=3,
      founder=1, prog=3, tech=3,
      why="ByteDance's recommendation platform with a Toronto office and heavy "
          "applied-ML and data work; a top brand in China, where he may return.",
      aliases=("ByteDance",), tags=("bigtech", "toronto", "ai", "china")),
    C("meta", "Meta", ca=2, us=3, cn=2, depth=2, role=2, domain=2, founder=1,
      prog=3, tech=3,
      why="Global engineering benchmark with a Toronto office and a structured, "
          "if very competitive, internship.",
      tags=("bigtech", "toronto")),
    C("apple", "Apple", ca=2, us=3, cn=3, depth=2, role=2, domain=2, founder=1,
      prog=3, tech=3,
      why="Toronto and Vancouver ML and hardware groups; elite brand in all "
          "three of his markets.",
      tags=("bigtech", "toronto")),
    C("oracle", "Oracle Canada", ca=2, us=3, cn=2, depth=3, role=3, domain=2,
      founder=1, prog=3, tech=2,
      why="Large enterprise-software and cloud employer with Canadian offices "
          "and a predictable student intake.",
      tags=("enterprise", "canada")),
    C("servicenow", "ServiceNow", ca=2, us=3, cn=1, depth=2, role=3, domain=2,
      founder=1, prog=3, tech=2,
      why="Fast-growing enterprise-workflow platform with Canadian hiring and a "
          "real internship.",
      tags=("enterprise", "canada")),
    C("cisco", "Cisco Canada", ca=2, us=3, cn=2, depth=3, role=3, domain=2,
      founder=1, prog=3, tech=2,
      why="Large Ottawa and Toronto R&D presence with one of the more reliable "
          "co-op intakes in Canadian enterprise tech.",
      tags=("enterprise", "canada")),
    C("workday", "Workday Canada", ca=2, us=3, cn=1, depth=2, role=3, domain=3,
      founder=1, prog=3, tech=2,
      why="Enterprise HR/finance cloud with Canadian offices and genuine data "
          "and analytics roles.",
      tags=("enterprise", "canada", "data")),
    C("block", "Block (Square)", ca=1, us=3, cn=1, depth=2, role=2, domain=3,
      founder=2, prog=3, tech=3,
      why="Fintech engineering brand (Square, Cash App) with Canadian remote "
          "hiring and a strong internship.",
      aliases=("Square",), tags=("fintech", "bigtech")),
    C("twilio2", "Twilio Canada", ca=1, us=2, cn=0, depth=2, role=2, domain=2,
      founder=1, prog=2, tech=2,
      why="Communications-API platform with Canadian remote engineering roles.",
      aliases=("Twilio",), tags=("saas", "canada")),
    C("doordash", "DoorDash", ca=2, us=3, cn=0, depth=2, role=3, domain=3,
      founder=2, prog=3, tech=2,
      why="Large marketplace with a Toronto office and genuinely interesting "
          "logistics and demand data work.",
      tags=("bigtech", "toronto", "data")),
    C("wayfair", "Wayfair", ca=1, us=2, cn=0, depth=2, role=3, domain=3,
      founder=1, prog=3, tech=2,
      why="E-commerce company with a real Toronto data-science and engineering "
          "centre and a structured co-op.",
      tags=("commerce", "toronto", "data")),
    C("pinterest", "Pinterest", ca=1, us=2, cn=0, depth=1, role=2, domain=3,
      founder=1, prog=3, tech=2,
      why="Large consumer-ML and data platform with a Toronto presence.",
      tags=("bigtech", "toronto", "data")),
    C("intel", "Intel Canada", ca=1, us=3, cn=2, depth=2, role=2, domain=1,
      founder=1, prog=3, tech=2,
      why="Toronto and Vancouver engineering sites; strong brand, work skews "
          "toward hardware and systems.",
      tags=("hardware", "canada")),
    C("qualcomm", "Qualcomm Canada", ca=1, us=3, cn=2, depth=2, role=1,
      domain=1, founder=1, prog=3, tech=2,
      why="Wireless and silicon engineering in Canada; prestigious but far "
          "from his analyst and product path.",
      tags=("hardware", "canada")),
    C("unity", "Unity", ca=1, us=2, cn=1, depth=2, role=2, domain=2, founder=1,
      prog=2, tech=2,
      why="Real-time 3D engine with Canadian offices and data/ML roles behind "
          "the games platform.",
      tags=("saas", "canada", "gaming")),
]

# =========================================================================
# More Canadian technology scale-ups, sector-agnostic — the breadth the
# candidate asked for beyond health.
# =========================================================================
_CANADA_TECH_2: list[CompanyProfile] = [
    C("indexexchange", "Index Exchange", ca=2, us=2, cn=0, depth=3, role=3,
      domain=3, founder=1, prog=3, tech=2,
      why="Toronto advertising exchange operating at enormous scale — heavy "
          "distributed-systems and data engineering, and a strong co-op intake. "
          "A clear omission from the registry.",
      tags=("saas", "toronto", "data", "adtech")),
    C("snyk", "Snyk", ca=1, us=2, cn=0, depth=2, role=3, domain=3, founder=2,
      prog=2, tech=3,
      why="Ottawa-rooted developer-security platform with a strong engineering "
          "brand and real Canadian hiring.",
      tags=("saas", "canada", "security")),
    C("klipfolio", "Klipfolio", ca=1, us=1, cn=0, depth=1, role=3, domain=3,
      founder=2, prog=2, tech=1,
      why="Ottawa BI and dashboard company — directly aligned with his Power BI "
          "and analytics work, at an accessible hiring bar.",
      tags=("saas", "canada", "data")),
    C("rewind", "Rewind", ca=1, us=1, cn=0, depth=1, role=2, domain=2,
      founder=2, prog=1, tech=2,
      why="Ottawa SaaS backup company; small, technical, and locally reachable.",
      tags=("saas", "canada")),
    C("symend", "Symend", ca=1, us=1, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=1, tech=2,
      why="Calgary behavioural-AI company for debt resolution — applied ML on "
          "financial-behaviour data.",
      tags=("saas", "canada", "ai", "fintech")),
    C("introhive", "Introhive", ca=1, us=1, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=2, tech=2,
      why="Fredericton/Toronto relationship-intelligence AI with a real data "
          "team.",
      tags=("saas", "canada", "ai")),
    C("tealbook", "Tealbook", ca=1, us=1, cn=0, depth=1, role=2, domain=3,
      founder=3, prog=1, tech=2,
      why="Toronto supplier-data-intelligence company; small, data-centric, and "
          "close to the customer.",
      tags=("saas", "toronto", "data", "ai")),
    C("roserocket", "Rose Rocket", ca=1, us=1, cn=0, depth=1, role=2, domain=3,
      founder=3, prog=1, tech=2,
      why="Toronto logistics-SaaS with real data work at a size where a co-op "
          "sees the whole product.",
      tags=("saas", "toronto", "tob")),
    C("nulogy", "Nulogy", ca=1, us=1, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=2, tech=2,
      why="Toronto supply-chain SaaS with genuine data engineering and a "
          "recurring intake.",
      tags=("saas", "toronto", "tob")),
    C("assent", "Assent", ca=1, us=1, cn=0, depth=2, role=3, domain=3,
      founder=2, prog=3, tech=2,
      why="Ottawa supply-chain-sustainability data company with a large, "
          "growing co-op programme.",
      tags=("saas", "canada", "data")),
    C("certn", "Certn", ca=1, us=1, cn=0, depth=2, role=2, domain=3, founder=2,
      prog=2, tech=2,
      why="Victoria background-check platform built on data pipelines and "
          "risk models.",
      tags=("saas", "canada", "data")),
    C("enghouse", "Enghouse Systems", ca=2, us=1, cn=0, depth=3, role=2,
      domain=2, founder=1, prog=2, tech=1,
      why="Large Markham enterprise-software acquirer with steady, if "
          "unglamorous, engineering hiring.",
      tags=("saas", "toronto")),
    C("touchbistro", "TouchBistro", ca=2, us=1, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=2, tech=2,
      why="Toronto restaurant-SaaS with a real product-and-data team.",
      tags=("saas", "toronto", "tob")),
    C("rangle", "Rangle.io", ca=1, us=1, cn=0, depth=2, role=2, domain=2,
      founder=2, prog=1, tech=2,
      why="Toronto engineering consultancy with a genuine technical reputation "
          "and varied client work.",
      tags=("saas", "toronto", "consulting")),
    C("later", "Later", ca=2, us=1, cn=0, depth=2, role=2, domain=3, founder=2,
      prog=2, tech=2,
      why="Vancouver social-media-management SaaS with data and analytics roles.",
      tags=("saas", "canada")),
]

# =========================================================================
# Gaming and interactive — data-, ML- and analytics-heavy, and among the
# largest co-op employers in Montreal and Toronto.
# =========================================================================
_GAMING: list[CompanyProfile] = [
    C("ubisoft", "Ubisoft", ca=3, us=2, cn=2, depth=3, role=3, domain=2,
      founder=1, prog=3, tech=2,
      why="Montreal and Toronto studios run one of the largest co-op intakes in "
          "Canada, with real data, ML and tools engineering behind the games.",
      tags=("gaming", "canada", "data")),
    C("ea", "Electronic Arts", ca=2, us=3, cn=2, depth=3, role=3, domain=2,
      founder=1, prog=3, tech=2,
      why="Large Vancouver and Montreal studios with heavy data-science and "
          "backend work and a mature co-op programme.",
      aliases=("EA",), tags=("gaming", "canada", "data")),
    C("behaviour", "Behaviour Interactive", ca=2, us=1, cn=1, depth=3, role=2,
      domain=2, founder=1, prog=3, tech=2,
      why="Canada's largest independent studio (Montreal) with real backend, "
          "data and live-ops engineering.",
      tags=("gaming", "canada")),
    C("gameloft", "Gameloft", ca=1, us=1, cn=2, depth=2, role=2, domain=2,
      founder=1, prog=2, tech=2,
      why="Montreal and Toronto mobile-games studios with data and backend "
          "roles.",
      tags=("gaming", "canada")),
    C("wbgames", "Warner Bros. Games Montreal", ca=1, us=2, cn=1, depth=2,
      role=2, domain=2, founder=1, prog=2, tech=2,
      why="Montreal AAA studio with engineering and tools roles.",
      tags=("gaming", "canada")),
    C("kabam", "Kabam", ca=1, us=1, cn=1, depth=2, role=2, domain=3, founder=1,
      prog=2, tech=2,
      why="Vancouver mobile-games studio with genuine data-science and "
          "live-analytics work.",
      tags=("gaming", "canada", "data")),
    C("eidos", "Eidos-Montréal", ca=1, us=1, cn=0, depth=2, role=2, domain=1,
      founder=1, prog=2, tech=2,
      why="Montreal AAA studio; engineering roles, French an asset.",
      tags=("gaming", "canada")),
]

# =========================================================================
# More insurers. His two-part frequency/severity GLM pricing project reads
# directly onto actuarial and pricing data-science teams here, which are an
# under-noticed but sizeable source of analyst roles.
# =========================================================================
_INSURANCE_2: list[CompanyProfile] = [
    C("cooperators", "Co-operators", ca=2, us=0, cn=0, depth=3, role=3,
      domain=3, founder=1, prog=3, tech=1,
      why="Guelph insurer with a large actuarial and data-science organisation "
          "and a strong co-op programme — a direct match for his GLM pricing "
          "work.",
      role_floor=True, tags=("insurer", "canada", "data")),
    C("wawanesa", "Wawanesa", ca=2, us=0, cn=0, depth=2, role=3, domain=2,
      founder=1, prog=2, tech=1,
      why="Large Winnipeg mutual insurer with actuarial and analytics roles.",
      role_floor=True, tags=("insurer", "canada")),
    C("goremutual", "Gore Mutual", ca=1, us=0, cn=0, depth=2, role=3, domain=2,
      founder=1, prog=2, tech=2,
      why="Cambridge insurer mid-way through a digital and data transformation, "
          "hiring analysts and data roles.",
      role_floor=True, tags=("insurer", "canada")),
    C("iafinancial", "iA Financial", ca=2, us=0, cn=0, depth=2, role=3,
      domain=2, founder=1, prog=2, tech=1,
      why="Quebec City insurer and wealth manager with actuarial and data "
          "teams; French an asset.",
      role_floor=True, tags=("insurer", "canada")),
    C("empirelife", "Empire Life", ca=1, us=0, cn=0, depth=2, role=3, domain=2,
      founder=1, prog=2, tech=1,
      why="Kingston insurer with actuarial and analytics co-op roles.",
      role_floor=True, tags=("insurer", "canada")),
    C("equitablelife", "Equitable Life", ca=1, us=0, cn=0, depth=2, role=3,
      domain=2, founder=1, prog=2, tech=1,
      why="Waterloo mutual insurer with a steady actuarial and data intake.",
      role_floor=True, tags=("insurer", "canada")),
    C("munichre", "Munich Re Canada", ca=1, us=1, cn=1, depth=2, role=2,
      domain=3, founder=1, prog=2, tech=2,
      why="Toronto reinsurance office with genuinely quantitative pricing and "
          "risk-modelling work.",
      role_floor=True, tags=("insurer", "toronto", "quant")),
    C("foresters", "Foresters Financial", ca=1, us=1, cn=0, depth=2, role=2,
      domain=2, founder=1, prog=2, tech=1,
      why="Toronto life insurer with data and analytics roles.",
      role_floor=True, tags=("insurer", "toronto")),
]

# =========================================================================
# Retail and commerce — rated ONLY where a real data-science / engineering
# organisation exists. The store-operations reporting trap he flagged is still
# excluded; these are the technology arms.
# =========================================================================
_RETAIL_TECH: list[CompanyProfile] = [
    C("canadiantire", "Canadian Tire (Data & Analytics)", ca=3, us=0, cn=0,
      depth=3, role=3, domain=3, founder=1, prog=3, tech=2,
      why="Runs one of the larger retail data-science and analytics "
          "organisations in Toronto, with a real co-op intake. Rated as its "
          "technology arm, not its stores.",
      aliases=("Canadian Tire",), role_floor=True,
      tags=("commerce", "toronto", "data")),
    C("lululemon", "lululemon (Tech)", ca=2, us=2, cn=2, depth=3, role=3,
      domain=3, founder=1, prog=3, tech=2,
      why="Large Vancouver technology and data organisation behind the brand, "
          "with genuine engineering and data-science co-op roles.",
      aliases=("lululemon", "Lululemon"), role_floor=True,
      tags=("commerce", "canada", "data")),
    C("aritzia", "Aritzia (Tech)", ca=2, us=1, cn=1, depth=2, role=3, domain=3,
      founder=1, prog=2, tech=2,
      why="Vancouver fashion retailer with a growing data and e-commerce "
          "engineering team.",
      aliases=("Aritzia",), role_floor=True, tags=("commerce", "canada", "data")),
    C("sobeysdigital", "Sobeys Digital (Voilà)", ca=2, us=0, cn=0, depth=2,
      role=3, domain=2, founder=1, prog=2, tech=2,
      why="The technology arm behind Sobeys' e-commerce (Voilà), with real data "
          "and platform engineering.",
      aliases=("Sobeys",), role_floor=True, tags=("commerce", "canada")),
]

# =========================================================================
# Hardware, robotics and space with substantial data/software work.
# =========================================================================
_DEEPTECH: list[CompanyProfile] = [
    C("cognitivesystems", "Cognitive Systems", ca=1, us=1, cn=0, depth=1,
      role=2, domain=3, founder=2, prog=2, tech=2,
      why="Waterloo wifi-sensing company doing genuine signal-processing and ML "
          "on the edge.",
      tags=("deeptech", "canada", "ai")),
    C("kepler", "Kepler Communications", ca=1, us=1, cn=0, depth=2, role=2,
      domain=2, founder=2, prog=2, tech=2,
      why="Toronto space-communications company with real software and data "
          "systems work.",
      tags=("deeptech", "toronto")),
    C("mda", "MDA Space", ca=2, us=1, cn=0, depth=3, role=2, domain=2,
      founder=1, prog=3, tech=2,
      why="Canada's flagship space-robotics company (BC/Ontario) with a large, "
          "established co-op programme.",
      tags=("deeptech", "canada", "robotics")),
]

# =========================================================================
# More health-data / clinical-AI (kept as one direction among several).
# =========================================================================
_HEALTH_2: list[CompanyProfile] = [
    C("semantichealth", "Semantic Health", ca=1, us=1, cn=0, depth=1, role=2,
      domain=3, founder=3, prog=1, tech=2,
      why="Toronto clinical-NLP and medical-coding AI — almost identical to his "
          "Remeda work mapping clinical text to standardised codes. The single "
          "closest match in the registry.",
      tags=("health", "toronto", "ai")),
    C("phenotips", "PhenoTips", ca=1, us=1, cn=0, depth=1, role=2, domain=3,
      founder=2, prog=1, tech=2,
      why="Toronto genomics and health-data platform used by hospitals.",
      tags=("health", "toronto", "data")),
    C("novari", "Novari Health", ca=1, us=0, cn=0, depth=1, role=2, domain=3,
      founder=2, prog=1, tech=1,
      why="Ontario health-workflow and e-referral software working directly "
          "with provincial health systems.",
      tags=("health", "canada")),
    C("cortico", "Cortico Health", ca=1, us=0, cn=0, depth=1, role=2, domain=3,
      founder=3, prog=1, tech=2,
      why="Toronto primary-care AI startup; small, close to clinical users.",
      tags=("health", "toronto", "ai")),
    C("proteinqure", "ProteinQure", ca=1, us=1, cn=0, depth=1, role=1, domain=3,
      founder=2, prog=1, tech=3,
      why="Toronto computational-protein-design company; deep ML, small and "
          "research-heavy.",
      tags=("health", "toronto", "ai")),
    C("telushealth", "TELUS Health", ca=3, us=1, cn=0, depth=3, role=3,
      domain=3, founder=1, prog=3, tech=2,
      why="Canada's largest digital-health organisation, with a broad clinical "
          "data footprint and a real student intake.",
      role_floor=True, tags=("health", "canada", "data")),
    C("medme", "MedMe Health", ca=1, us=0, cn=0, depth=1, role=2, domain=3,
      founder=3, prog=1, tech=2,
      why="Toronto pharmacy-software company scaling clinical services; a co-op "
          "sees product and customers.",
      tags=("health", "toronto")),
    C("rocketdoctor", "Rocket Doctor", ca=1, us=1, cn=0, depth=1, role=2,
      domain=3, founder=3, prog=1, tech=1,
      why="Toronto telemedicine platform with real health-data work at a small "
          "scale.",
      tags=("health", "toronto")),
]

# =========================================================================
# More fintech — payments, banking-as-a-service, SMB.
# =========================================================================
_FINTECH_2: list[CompanyProfile] = [
    C("flinks", "Flinks", ca=2, us=1, cn=0, depth=2, role=3, domain=3,
      founder=2, prog=2, tech=2,
      why="Montreal open-banking data platform (backed by National Bank) — "
          "fintech plus real data-pipeline engineering, a strong fit.",
      tags=("fintech", "canada", "data")),
    C("arteriaai", "Arteria AI", ca=1, us=1, cn=0, depth=2, role=2, domain=3,
      founder=3, prog=1, tech=2,
      why="Toronto AI for financial agreements and documentation — applied AI "
          "on financial data with enterprise buyers.",
      tags=("fintech", "toronto", "ai")),
    C("freshbooks", "FreshBooks", ca=2, us=1, cn=0, depth=3, role=3, domain=3,
      founder=2, prog=3, tech=2,
      why="Toronto cloud-accounting company and one of the larger local co-op "
          "employers; fintech-adjacent data and product work.",
      tags=("fintech", "toronto", "saas")),
    C("moneris", "Moneris", ca=3, us=0, cn=0, depth=3, role=3, domain=3,
      founder=1, prog=3, tech=1,
      why="Canada's largest payment processor (Toronto, RBC/BMO joint venture) "
          "with a big technology organisation and co-op intake.",
      role_floor=True, tags=("fintech", "toronto")),
    C("symcor", "Symcor", ca=1, us=0, cn=0, depth=3, role=3, domain=3,
      founder=1, prog=2, tech=1,
      why="Toronto financial-data-processing company owned by the big banks; "
          "large-scale data engineering, unglamorous but real.",
      role_floor=True, tags=("fintech", "toronto", "data")),
    C("nestwealth", "Nest Wealth", ca=1, us=0, cn=0, depth=1, role=2, domain=3,
      founder=2, prog=1, tech=2,
      why="Toronto robo-advisor and wealth-tech platform.",
      tags=("fintech", "toronto")),
    C("conquest", "Conquest Planning", ca=1, us=1, cn=0, depth=2, role=2,
      domain=3, founder=2, prog=1, tech=2,
      why="Winnipeg/Toronto financial-planning AI, scaling fast with bank "
          "partnerships.",
      tags=("fintech", "canada", "ai")),
    C("brim", "Brim Financial", ca=1, us=1, cn=0, depth=2, role=2, domain=3,
      founder=3, prog=1, tech=2,
      why="Toronto credit-card-platform-as-a-service; real fintech engineering "
          "with enterprise customers.",
      tags=("fintech", "toronto")),
    C("relayfi", "Relay", ca=1, us=1, cn=0, depth=1, role=2, domain=3,
      founder=3, prog=1, tech=2,
      why="Toronto SMB banking platform; small, fast, close to the product.",
      tags=("fintech", "toronto")),
    C("loopfin", "Loop", ca=1, us=0, cn=0, depth=1, role=2, domain=3, founder=3,
      prog=1, tech=2,
      why="Toronto cross-border banking and cards for businesses.",
      tags=("fintech", "toronto")),
    C("caary", "Caary", ca=1, us=0, cn=0, depth=1, role=2, domain=3, founder=3,
      prog=1, tech=1,
      why="Toronto SMB credit and spend-management platform; small and "
          "close to the product.",
      tags=("fintech", "toronto")),
    C("nesto", "nesto", ca=1, us=0, cn=0, depth=2, role=2, domain=3, founder=2,
      prog=1, tech=2,
      why="Montreal digital-mortgage platform with real data and product work.",
      tags=("fintech", "canada")),
    C("ratehub", "Ratehub", ca=2, us=0, cn=0, depth=2, role=2, domain=3,
      founder=2, prog=1, tech=1,
      why="Toronto personal-finance marketplace and fintech.",
      tags=("fintech", "toronto")),
]

ALL_PROFILES: list[CompanyProfile] = [
    *_NAMED_TARGETS, *_HEALTH, *_AI, *_FINTECH, *_FINANCE, *_SAAS, *_GLOBAL,
    *_FINANCE_GLOBAL, *_HEALTH_DATA, *_RESEARCH, *_ENTERPRISE, *_CANADA_TECH,
    *_PUBLIC, *_INVESTMENT, *_GLOBAL_TECH_2, *_CANADA_TECH_2, *_GAMING,
    *_INSURANCE_2, *_RETAIL_TECH, *_DEEPTECH, *_HEALTH_2, *_FINTECH_2,
]
BY_KEY: dict[str, CompanyProfile] = {p.key: p for p in ALL_PROFILES}


# =========================================================================
# Deliberately NOT rated. Absence here is a decision, not an oversight.
# =========================================================================
EXCLUSIONS: dict[str, str] = {
    "Mining and resources (Barrick, Agnico, Teck, Nutrien)":
        "No analyst or product path he wants, and no domain that compounds.",
    "Oil and gas (Suncor, Cenovus, Enbridge, TC Energy)":
        "Same as mining. His Shell experience is a data story, not an intention "
        "to stay in energy.",
    "Grocery and general retail (Loblaw, Sobeys, Metro, Dollarama, "
    "Hudson's Bay, Indigo, Roots, Aritzia)":
        "Retail reporting seats are exactly the 'pure analyst with no customer "
        "contact' trap his own analysis tells him to avoid.",
    "Large IT outsourcing (Accenture, CGI, Infosys, Cognizant, Capgemini)":
        "Staffed onto client maintenance work: almost no product surface and no "
        "founding muscle.",
    "Big-four audit and tax streams (KPMG, PwC, EY, Deloitte audit lines)":
        "Not a data or product path. Their AI consulting arms are a separate "
        "question and are not currently rated either.",
    "Telecom (Bell, Rogers, TELUS)":
        "Technical share is diluted by retail and field headcount, and the "
        "analyst roles are reporting-shaped.",
    "Management consulting (McKinsey, BCG, Bain)":
        "Excellent brands, but the entry seat is not a data or product role and "
        "the path leads away from building.",
    "Defence and weapons (Anduril, and defence lines at Palantir)":
        "Excluded on his behalf pending an explicit decision from him; not "
        "assumed either way.",
    "Universities and school boards as employers":
        "Administrative data roles with no commercial exposure.",
    "Pure semiconductor and EDA firms (Synopsys, Cadence, Marvell, Qualcomm)":
        "Deep hardware paths with no analyst or product entry point for him.",
    "Government and municipal employers (City of Toronto, OPS, Metrolinx)":
        "Stable and local, but slow-moving reporting work with no founding "
        "value; kept out unless he says otherwise.",
}


# --------------------------------------------------------------------------
# Identity resolution — one employer resolves to exactly one profile.
# --------------------------------------------------------------------------
_ALIAS_INDEX: dict[str, str] = {}
for _p in ALL_PROFILES:
    _ALIAS_INDEX[_p.name.lower().replace(" ", "")] = _p.key
    _ALIAS_INDEX[_p.key] = _p.key
    for _a in _p.aliases:
        _ALIAS_INDEX[_a.lower().replace(" ", "")] = _p.key
    for _conn, _ext in _p.boards:
        _ALIAS_INDEX[f"{_conn}:{_ext}".lower()] = _p.key


def resolve(name_or_board: str) -> CompanyProfile | None:
    """Map a company name or 'connector:external_id' onto one canonical profile."""
    if not name_or_board:
        return None
    key = _ALIAS_INDEX.get(name_or_board.lower().replace(" ", ""))
    return BY_KEY[key] if key else None


class View(StrEnum):
    """The two rankings are named for the action they drive, not the formula.

    They answer different questions and must not be presented as competing
    versions of one list. Sorting by value alone puts OpenAI second, and an
    application there is time spent for a near-certain no; sorting by priority
    buries it, which is right for the application queue and wrong for deciding
    where a referral is worth chasing.
    """

    APPLY = "apply"      # sqrt(value x access): where applications should go
    VALUE = "value"      # value alone: what is worth wanting, however reachable
    PLATFORM = "platform"  # the company on its own terms


# Value has a different spread from the blended priority score, so it needs its
# own cut points rather than reusing the priority bands.
VALUE_BANDS: tuple[tuple[float, str], ...] = (
    (85.0, "S"), (74.0, "A"), (64.0, "B"), (52.0, "C"), (0.0, "D"),
)


def ranked(by: str = View.APPLY) -> list[CompanyProfile]:
    keys = {
        View.APPLY: lambda p: (-p.personal_score, p.name),
        View.VALUE: lambda p: (-p.value_score, p.name),
        View.PLATFORM: lambda p: (-p.platform_score, p.name),
        # Retained so existing callers keep working.
        "personal": lambda p: (-p.personal_score, p.name),
    }
    return sorted(ALL_PROFILES, key=keys.get(by, keys[View.APPLY]))


def tier_counts(by: str = "personal") -> dict[str, int]:
    out: dict[str, int] = {}
    for p in ALL_PROFILES:
        tier = p.personal_tier if by == "personal" else p.platform_tier
        out[tier] = out.get(tier, 0) + 1
    return {t: out.get(t, 0) for t in ("S", "A", "B", "C", "D")}


def adjustments() -> list[CompanyProfile]:
    """Every company where pass 2 moved what pass 1 produced."""
    return [p for p in ALL_PROFILES if p.adjusted]
