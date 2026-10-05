"""Decision points D3 (template parameters), D4 (repair) and the PR narrative.

Offline: rule-based defaults and templated prose. Local: the LLM chooses among allowed options and
writes prose; every response is schema-validated, re-asked once, then falls back to the rule path
(AGENTS.md "LLM usage rules"). Numbers never come from the model.
"""

from __future__ import annotations

from emissiongate.agents.context import RunContext
from emissiongate.agents.strategist import Strategy, rule_decision
from emissiongate.agents.validator import RepairFn, offline_repair
from emissiongate.contracts import Candidate, PatchDecision, PlanResult
from emissiongate.core import patches
from emissiongate.core.claims import any_numeric_claim
from emissiongate.core.interventions import Valuation
from emissiongate.report.render import TEMPLATE_NARRATIVE


def _llm_ready(ctx: RunContext) -> bool:
    return ctx.llm is not None and (ctx.budget is None or ctx.budget.can_call_llm())


def decide(ctx: RunContext, strategy: Strategy, candidate: Candidate) -> tuple[PatchDecision, str]:
    if _llm_ready(ctx):
        from emissiongate.llm import calls

        decision = calls.decide_patch(ctx, strategy, candidate)
        if decision is not None:
            errors = patches.validate_params(candidate, decision)
            if not errors:
                return decision, "llm"
            ctx.ledger.append(
                state=ctx.state,
                kind="fallback",
                agent="strategist",
                detail={"candidate_id": candidate.candidate_id, "reason": "; ".join(errors)[:300]},
            )
    return rule_decision(candidate), "rule"


def repair_fn(ctx: RunContext) -> RepairFn:
    if not _llm_ready(ctx):
        return offline_repair

    def repair(
        candidate: Candidate, decision: PatchDecision, result: PlanResult, attempt: int
    ) -> PatchDecision | None:
        from emissiongate.llm import calls

        if attempt == 2 and "bad-param" in ctx.inject:
            # The injected fault lives in the renderer, not the params: the model sees the stderr
            # and may confirm the same allowed params; validation then decides.
            pass
        fixed = calls.repair_params(ctx, candidate, decision, result)
        return fixed if fixed is not None else offline_repair(candidate, decision, result, attempt)

    return repair


def narrate(
    ctx: RunContext, candidate: Candidate, valuation: Valuation
) -> tuple[str, list[str], str]:
    """Return (narrative, risks, source). Source is 'llm' or 'template'."""
    if _llm_ready(ctx):
        from emissiongate.llm import calls

        got = calls.narrative(ctx, candidate, valuation)
        if got is not None:
            if not any_numeric_claim([got.summary, *got.risks]):
                return got.summary, list(got.risks), "llm"
            ctx.ledger.append(
                state=ctx.state,
                kind="fallback",
                agent="validator",
                detail={"candidate_id": candidate.candidate_id, "reason": "numeric_claim"},
            )
    return TEMPLATE_NARRATIVE[candidate.intervention], [], "template"
