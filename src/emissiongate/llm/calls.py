"""LLM call sites: patch decision, parameter repair (large tier) and PR narrative (small tier).

Each call is ledgered with model, reasoning level, prompt and completion tokens (thinking included),
duration, attempt and outcome. Prompts receive typed facts and allowed options; they never receive
figures the model is expected to restate. `ctx` is the run context (duck-typed: llm/ never imports
agents/).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel

from emissiongate.contracts import Candidate, Narrative, PatchDecision, PlanResult
from emissiongate.core.interventions import Valuation
from emissiongate.llm.client import Tier, structured

PROMPTS = Path(__file__).parent / "prompts"
DECISION_TEMPERATURE = 0.0
NARRATIVE_TEMPERATURE = 0.3
_env = Environment(
    loader=FileSystemLoader(str(PROMPTS)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=False,
)


def _render(name: str, **facts: object) -> str:
    return _env.get_template(name).render(**facts)


def _call[M: BaseModel](
    ctx: Any,
    call_site: str,
    tier: Tier,
    template: str,
    schema: type[M],
    temperature: float,
    **facts: object,
) -> M | None:
    system = _render("system.j2")
    prompt = _render(template, **facts)
    parsed, records = structured(
        ctx.llm.transport,
        tier,
        [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        schema,
        temperature,
    )
    for rec in records:
        ctx.ledger.append(
            state=ctx.state,
            kind="llm_call",
            agent="validator" if call_site in ("repair_params", "narrative") else "strategist",
            model=tier.label,
            prompt_tokens=rec.prompt_tokens,
            completion_tokens=rec.completion_tokens,
            duration_ms=rec.duration_ms,
            attempt=rec.attempt,
            payload={"prompt": prompt},
            detail={
                "call_site": call_site,
                "outcome": rec.outcome,
                "think": rec.think,
                "thinking_sha256": rec.thinking_sha256,
                "error": rec.error,
            },
        )
        if ctx.budget is not None:
            ctx.budget.charge_llm(rec.prompt_tokens + rec.completion_tokens)
    if parsed is None:
        ctx.ledger.append(
            state=ctx.state,
            kind="fallback",
            agent="strategist",
            detail={"call_site": call_site, "reason": "schema_invalid_after_reask_or_error"},
        )
    return parsed


def decide_patch(ctx: Any, strategy: Any, candidate: Candidate) -> PatchDecision | None:
    f = strategy.facts[candidate.resource_id]
    alternatives = strategy.alternatives.get(candidate.resource_id, [])
    return _call(
        ctx,
        "decide_patch",
        ctx.llm.large,
        "decide_patch.j2",
        PatchDecision,
        DECISION_TEMPERATURE,
        candidate=candidate,
        resource=f.resource,
        util=f.util,
        alternatives=[a.intervention for a in alternatives],
    )


def repair_params(
    ctx: Any, candidate: Candidate, decision: PatchDecision, result: PlanResult
) -> PatchDecision | None:
    return _call(
        ctx,
        "repair_params",
        ctx.llm.large,
        "repair_params.j2",
        PatchDecision,
        DECISION_TEMPERATURE,
        candidate=candidate,
        decision=decision,
        stderr=result.stderr_tail[-2000:],
        command=result.command,
    )


def narrative(ctx: Any, candidate: Candidate, valuation: Valuation) -> Narrative | None:
    return _call(
        ctx,
        "narrative",
        ctx.llm.small,
        "narrative.j2",
        Narrative,
        NARRATIVE_TEMPERATURE,
        candidate=candidate,
        notes=list(valuation.notes),
        params=valuation.params,
    )
