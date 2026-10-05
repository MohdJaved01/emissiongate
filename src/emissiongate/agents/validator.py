"""Validator: render the decided template, prove it with tofu, repair at most N times, draft the PR.

No PR draft without a passing fmt/validate/plan (AGENTS.md invariant 7). When repairs are spent the
candidate is escalated with the plan error attached; it never loops.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable
from dataclasses import dataclass, field

from emissiongate.agents.context import RunContext
from emissiongate.contracts import Candidate, PatchDecision, PlanResult, PullRequestDraft
from emissiongate.core import patches
from emissiongate.core.interventions import ResourceFacts
from emissiongate.tools.tf import Workspace

RepairFn = Callable[[Candidate, PatchDecision, PlanResult, int], PatchDecision | None]


@dataclass
class Validation:
    candidate: Candidate
    decision: PatchDecision
    attempts: list[PlanResult] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    diff: str = ""
    ok: bool = False
    error: str | None = None
    event_ids: list[int] = field(default_factory=list)

    @property
    def first_attempt_ok(self) -> bool:
        return bool(self.attempts) and self.attempts[0].ok


def unified_diff(path: str, old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def offline_repair(
    candidate: Candidate, decision: PatchDecision, result: PlanResult, attempt: int
) -> PatchDecision | None:
    """Rule-based repair: retry with the next allowed value of the first parameter."""
    opt = candidate.options[0]
    current = decision.params.get(opt.name)
    remaining = [v for v in opt.allowed if v != current]
    if attempt == 2:
        # An injected failure only affects the first render; the same params are retried once.
        return decision
    if not remaining:
        return None
    params = dict(decision.params) | {opt.name: remaining[0]}
    return decision.model_copy(update={"params": params, "rationale": "offline repair"})


def validate(
    ctx: RunContext,
    ws: Workspace,
    facts: ResourceFacts,
    candidate: Candidate,
    decision: PatchDecision,
    forbid: tuple[str, ...],
    repair: RepairFn,
    max_attempts: int,
) -> Validation:
    v = Validation(candidate=candidate, decision=decision)
    resource = facts.resource
    assert resource.tf_file is not None
    original = (ctx.estate_dir / resource.tf_file).read_text(encoding="utf-8")
    inject = "bad-param" in ctx.inject and candidate.intervention == "graviton"
    for attempt in range(1, max_attempts + 1):
        try:
            files = patches.render(
                decision.template,
                resource,
                original,
                decision.params,
                forbid=forbid,
                inject_bad_param=inject and attempt == 1,
            )
        except (patches.PatchError, KeyError, ValueError) as exc:
            v.error = f"render failed: {exc}"
            break
        start = len(ws.history)
        result = ws.check(files, attempt=attempt)
        for cmd in ws.history[start:]:
            ctx.ledger.append(
                state=ctx.state,
                kind="tool_call",
                agent="validator",
                tool=f"tofu.{cmd.args[0]}",
                duration_ms=cmd.duration_ms,
                attempt=attempt,
                detail={"candidate_id": candidate.candidate_id, "exit_code": cmd.exit_code},
            )
        v.attempts.append(result)
        event = ctx.ledger.append(
            state=ctx.state,
            kind="decision",
            agent="validator",
            attempt=attempt,
            payload={"decision": decision.model_dump(), "plan": result.model_dump()},
            detail={
                "candidate_id": candidate.candidate_id,
                "plan_ok": result.ok,
                "command": result.command,
            },
        )
        v.event_ids.append(event.seq)
        if result.ok:
            v.ok = True
            v.decision = decision
            v.files = files
            v.diff = unified_diff(resource.tf_file, original, files[resource.tf_file])
            break
        if ctx.budget is not None:
            ctx.budget.charge_repair()
        if attempt == max_attempts:
            v.error = f"plan failed after {attempt} attempts"
            break
        nxt = repair(candidate, decision, result, attempt + 1)
        if nxt is None:
            v.error = "no repair available"
            break
        errors = patches.validate_params(candidate, nxt)
        if errors:
            ctx.ledger.append(
                state=ctx.state,
                kind="fallback",
                agent="validator",
                detail={"candidate_id": candidate.candidate_id, "reason": "; ".join(errors)[:300]},
            )
            nxt = offline_repair(candidate, decision, result, attempt + 1)
            if nxt is None:
                v.error = "no valid repair"
                break
        decision = nxt
    if not v.ok and v.error is None:
        v.error = "validation failed"
    return v


def draft(
    candidate: Candidate, validation: Validation, title: str, body_md: str
) -> PullRequestDraft:
    return PullRequestDraft(
        candidate_id=candidate.candidate_id,
        branch=f"emissiongate/{candidate.resource_id}-{candidate.intervention}",
        title=title,
        body_md=body_md,
        files=validation.files,
        labels=["emissiongate", f"eg/{candidate.intervention}", "synthetic"],
        status="drafted" if validation.ok else "escalated",
    )
