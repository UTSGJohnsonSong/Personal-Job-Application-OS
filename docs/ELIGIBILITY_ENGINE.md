# Eligibility Engine

Deterministic, explainable, evidence-bearing. It answers: *is the user allowed to
apply / likely to pass the hard gate?* — separate from ranking (fit/quality).

## Verdicts
`eligible` · `likely_eligible` · `uncertain` · `likely_ineligible` · `ineligible`.

## Every result carries
- `reasons[]` (human-readable)
- `jd_evidence[]` (verbatim spans from the posting)
- `context_evidence[]` (which Personal Context items were used)
- `conflicts[]` (JD requirement vs known fact)
- `unknowns[]` (requirement we can't evaluate from confirmed context)
- `needs_user_confirmation` (true when a hard gate depends on unconfirmed context)

## Rule checks (v1)
Evaluated as independent, explainable checks that each output a
`CheckOutcome{pass|fail|unknown, weight, evidence}`:
- work authorization / sponsorship vs JD requirement,
- degree level & graduation-timing window,
- employment type (intern/co-op/new-grad/full-time) vs candidate target,
- hard "must-have" credentials/licenses/languages explicitly required,
- location/remote compatibility when the JD hard-requires on-site in a region.

## Aggregation (no black box)
- Any hard check `fail` with strong evidence → `ineligible`.
- Any hard check `fail` with weak/uncertain evidence → `likely_ineligible`.
- All hard checks `pass` → `eligible`.
- Mix of pass + unknown on hard gates → `uncertain` (surfaced, **never
  auto-skipped, never auto-answered**).
- Unknowns on soft/"preferred" items never reduce below `likely_eligible`.

The mapping table lives in `app/eligibility/engine.py` and is unit-tested with
fixture JDs + synthetic contexts.
