"""Strategist: guardrails first, then eligible templates, savings, thresholds and carbon ranking."""

from __future__ import annotations

from dataclasses import dataclass, field

from emissiongate.agents.context import RunContext
from emissiongate.contracts import Advisory, Candidate, EmissionRecord, ParamOption, PatchDecision
from emissiongate.core import interventions as iv
from emissiongate.core.policy import Verdict
from emissiongate.core.ranking import best_per_resource, key, rank

IDLE_EBS_DAYS = 30


@dataclass
class Strategy:
    candidates: list[Candidate] = field(default_factory=list)  # deliverable, carbon order
    alternatives: dict[str, list[Candidate]] = field(default_factory=dict)  # by resource
    valuations: dict[str, iv.Valuation] = field(default_factory=dict)  # every valued option
    ranks_all: dict[str, tuple[int, int]] = field(default_factory=dict)
    advisories: list[Advisory] = field(default_factory=list)
    verdicts: dict[str, Verdict] = field(default_factory=dict)
    no_action: dict[str, list[str]] = field(default_factory=dict)
    facts: dict[str, iv.ResourceFacts] = field(default_factory=dict)


Option = tuple[list[ParamOption], dict[str, str], iv.Valuation]


def _rightsize(ctx: RunContext, f: iv.ResourceFacts, reasons: list[str]) -> Option | None:
    assert ctx.prices is not None
    allowed = iv.rightsize_options(
        f, ctx.factors, ctx.policy.thresholds["rightsize_target_p95_max"]
    )
    if not allowed:
        reasons.append("rightsize: no smaller size keeps projected p95 under the limit")
        return None
    opts = [ParamOption(name="target_instance_type", allowed=allowed)]
    params = {"target_instance_type": allowed[0]}
    return opts, params, iv.value_rightsize(f, ctx.factors, ctx.prices, allowed[0])


def _graviton(ctx: RunContext, f: iv.ResourceFacts, reasons: list[str]) -> Option | None:
    assert ctx.prices is not None
    allowed = iv.graviton_options(f, ctx.factors)
    if not allowed:
        reasons.append("graviton: already arm64 or no arm64 equivalent in the factors file")
        return None
    opts = [
        ParamOption(name="target_instance_type", allowed=allowed),
        ParamOption(name="image_param", allowed=["ami_arm64"]),
    ]
    params = {"target_instance_type": allowed[0], "image_param": "ami_arm64"}
    return opts, params, iv.value_graviton(f, ctx.factors, ctx.prices, allowed[0])


def _schedule(ctx: RunContext, f: iv.ResourceFacts, reasons: list[str]) -> Option | None:
    assert ctx.prices is not None
    r = f.resource
    if r.kind != "ec2_asg":
        return None
    if not ctx.policy.schedule_allowed(r.tags):
        reasons.append(f"schedule: not allowed for Environment={r.tags.get('Environment')}")
        return None
    ok, why = iv.schedule_eligible(f, ctx.policy.thresholds)
    if not ok:
        reasons.append(f"schedule: {why}")
        return None
    shape = iv.schedule_shape(f.util, r.region, ctx.reference)
    if shape is None:
        reasons.append("schedule: activity mask is not one daily span")
        return None
    opts = iv.schedule_options(shape, r.count)
    params = {o.name: o.allowed[0] for o in opts}
    return opts, params, iv.value_schedule(f, ctx.factors, ctx.prices, params)


def _storage_tier(ctx: RunContext, f: iv.ResourceFacts, reasons: list[str]) -> Option | None:
    assert ctx.prices is not None
    if f.resource.kind != "s3" or f.meta.get("lifecycle", True):
        return None
    opts = [
        ParamOption(name="transition_days", allowed=list(iv.STORAGE_TIER_DAYS)),
        ParamOption(name="storage_class", allowed=list(iv.STORAGE_TIER_CLASSES)),
    ]
    params = {"transition_days": "90", "storage_class": "GLACIER_IR"}
    return opts, params, iv.value_storage_tier(f, ctx.factors, ctx.prices, params)


def _time_shift(ctx: RunContext, f: iv.ResourceFacts, reasons: list[str]) -> Option | None:
    r = f.resource
    if not (f.meta.get("schedules") or {}).get("up"):
        return None
    snap = ctx.grid_snapshot
    if snap is None or r.region != snap.region:
        reasons.append("time_shift: no live or snapshot grid data for this region")
        return None
    window = ctx.policy.thresholds["time_shift_allowed_window"]
    ranked, scored, current = iv.time_shift_options(f, snap, window, ctx.reference)
    if not ranked or ranked[0] == current:
        reasons.append("time_shift: current window is already the lowest-intensity one")
        return None
    opts = [ParamOption(name="start_cron", allowed=ranked)]
    value = iv.value_time_shift(f, ctx.factors, snap, scored, current, ranked[0])
    return opts, {"start_cron": ranked[0]}, value


BUILDERS = {
    "rightsize": _rightsize,
    "graviton": _graviton,
    "schedule": _schedule,
    "storage_tier": _storage_tier,
    "time_shift": _time_shift,
}


def strategise(
    ctx: RunContext, facts: list[iv.ResourceFacts], records: dict[str, EmissionRecord]
) -> Strategy:
    th = ctx.policy.thresholds
    s = Strategy()
    above: list[iv.Valuation] = []
    options: dict[str, tuple[list[ParamOption], dict[str, str]]] = {}
    for f in sorted(facts, key=lambda x: x.resource.resource_id):
        r = f.resource
        s.facts[r.resource_id] = f
        verdict = ctx.policy.evaluate(r, ctx.today)
        s.verdicts[r.resource_id] = verdict
        if r.resource_id not in records:
            continue  # not quantified: counted in coverage
        if verdict.refused:
            reason = (
                "suppressed by a human rejection"
                if verdict.suppressed_by and not verdict.blocked_by
                else "guardrail: protected resource, no change is proposed (fail closed)"
            )
            s.advisories.append(
                Advisory(
                    resource_id=r.resource_id,
                    kind="guardrail",
                    reason=reason,
                    blocked_by=list(verdict.blocked_by) + list(verdict.suppressed_by),
                )
            )
            continue
        if not f.util.sufficient:
            s.advisories.append(
                Advisory(
                    resource_id=r.resource_id,
                    kind="insufficient_evidence",
                    reason=f.util.reason or "insufficient datapoints",
                )
            )
            continue
        if r.kind == "ebs" and r.attached is False:
            days = int(f.meta.get("unattached_days", 0))
            if days >= IDLE_EBS_DAYS:
                s.advisories.append(
                    Advisory(
                        resource_id=r.resource_id,
                        kind="decommission",
                        reason=f"unattached for {days} days; deleting data is a human decision",
                        kg_co2e_saved_yr=records[r.resource_id].kg_co2e_yr,
                    )
                )
                continue
        reasons: list[str] = []
        valued = False
        for intervention in verdict.allowed:
            got = BUILDERS[intervention](ctx, f, reasons)
            if got is None:
                continue
            valued = True
            opts, params, value = got
            cid = key(value)
            s.valuations[cid] = value
            options[cid] = (opts, params)
            if value.kg_co2e_saved_yr < th["min_saving_kg_co2e_yr"]:
                s.advisories.append(
                    Advisory(
                        resource_id=r.resource_id,
                        kind="below_threshold",
                        reason=(
                            f"{intervention}: carbon saving below min_saving_kg_co2e_yr "
                            f"({th['min_saving_kg_co2e_yr']}); synthetic cost saving "
                            f"{value.usd_synthetic_saved_yr:,.0f} USD/yr"
                        ),
                        blocked_by=list(verdict.blocked_by),
                        kg_co2e_saved_yr=value.kg_co2e_saved_yr,
                    )
                )
            else:
                above.append(value)
        if not valued:
            s.no_action[r.resource_id] = reasons or ["no applicable template"]
            if any(x.startswith("time_shift: no live") for x in reasons):
                s.advisories.append(
                    Advisory(
                        resource_id=r.resource_id,
                        kind="insufficient_evidence",
                        reason="time_shift needs live or snapshot grid data for this region",
                    )
                )

    s.ranks_all = rank(list(s.valuations.values()))
    deliverable = best_per_resource(above)
    ranks = rank(deliverable)

    def to_candidate(v: iv.Valuation, rc: tuple[int, int]) -> Candidate:
        opts, params = options[key(v)]
        return Candidate(
            candidate_id=key(v),
            resource_id=v.resource_id,
            intervention=v.intervention,
            options=opts,
            default_params=params,
            kg_co2e_saved_yr=v.kg_co2e_saved_yr,
            kwh_saved_yr=v.kwh_saved_yr,
            usd_synthetic_saved_yr=v.usd_synthetic_saved_yr,
            rank_carbon=rc[0],
            rank_cost=rc[1],
            confidence=v.confidence,  # type: ignore[arg-type]
        )

    s.candidates = [to_candidate(v, ranks[key(v)]) for v in deliverable]
    for v in above:
        if key(v) not in ranks:
            s.alternatives.setdefault(v.resource_id, []).append(
                to_candidate(v, s.ranks_all[key(v)])
            )
    ctx.ledger.append(
        state=ctx.state,
        kind="decision",
        agent="strategist",
        payload={"candidates": [c.model_dump() for c in s.candidates]},
        detail={
            "candidates": len(s.candidates),
            "advisories": len(s.advisories),
            "carbon_order": ",".join(c.resource_id for c in s.candidates),
        },
    )
    return s


def rule_decision(candidate: Candidate) -> PatchDecision:
    return PatchDecision(
        candidate_id=candidate.candidate_id,
        template=candidate.intervention,
        params=dict(candidate.default_params),
        rationale="Rule-based default (offline behaviour).",
    )


def revalue(ctx: RunContext, s: Strategy, decision: PatchDecision) -> iv.Valuation:
    """Recompute savings in core for the decided template and parameters."""
    f = s.facts[decision.candidate_id.split(":")[0]]
    assert ctx.prices is not None
    p = decision.params
    if decision.template == "rightsize":
        return iv.value_rightsize(f, ctx.factors, ctx.prices, p["target_instance_type"])
    if decision.template == "graviton":
        return iv.value_graviton(f, ctx.factors, ctx.prices, p["target_instance_type"])
    if decision.template == "schedule":
        return iv.value_schedule(f, ctx.factors, ctx.prices, p)
    if decision.template == "storage_tier":
        return iv.value_storage_tier(f, ctx.factors, ctx.prices, p)
    if decision.template == "time_shift":
        snap = ctx.grid_snapshot
        assert snap is not None
        window = ctx.policy.thresholds["time_shift_allowed_window"]
        _, scored, current = iv.time_shift_options(f, snap, window, ctx.reference)
        return iv.value_time_shift(f, ctx.factors, snap, scored, current, p["start_cron"])
    raise ValueError(f"unknown template {decision.template}")
