"""Gate verdict (GATE §3): the net carbon delta of a pull request and the status it earns.

Shared by the evaluate step and the publish step, so the privileged step re-derives the status from
the projections with its own trusted policy instead of trusting a status it was handed
(THREAT_MODEL B5). Acknowledgement is not decided here; it needs server-side records.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from emissiongate.contracts import Projection

INPUT_STATUSES = frozenset({"pass", "not_evaluated"})
CONCLUSIONS = {
    "pass": "success",
    "pass_with_warning": "success",
    "accepted": "success",
    "ack_required": "failure",
}
NOT_EVALUATED_CONCLUSIONS = frozenset({"neutral", "failure"})


@dataclass(frozen=True)
class Totals:
    net: float
    low: float
    high: float


def _band(p: Projection, which: str) -> float:
    after = getattr(p, f"kg_co2e_yr_after_{which}")
    before = getattr(p, f"kg_co2e_yr_before_{which}")
    a = p.kg_co2e_yr_after if after is None else after
    b = p.kg_co2e_yr_before if before is None else before
    return a - b


def totals(projections: list[Projection]) -> Totals:
    """Net kgCO2e/yr over quantified rows; assumed rows contribute their band to low and high."""
    q = [p for p in projections if p.quantified]
    net = sum(p.kg_co2e_yr_after - p.kg_co2e_yr_before for p in q)
    low = sum(_band(p, "low") for p in q)
    high = sum(_band(p, "high") for p in q)
    return Totals(net, min(low, high), max(low, high))


def verdict(
    prior: str, projections: list[Projection], gate_cfg: dict
) -> tuple[str, str | None, Totals]:
    """(status, reason, totals). `prior` is "pass" (evaluated) or "not_evaluated".

    Thresholds are inclusive and come from `policy.yaml -> gate`; a missing key or a
    non-finite total raises.
    """
    if prior not in INPUT_STATUSES:
        raise ValueError(f"verdict input status must be pass or not_evaluated, got {prior!r}")
    t = totals(projections)
    if not all(math.isfinite(x) for x in (t.net, t.low, t.high)):
        # NaN compares false with every threshold, which would read as a pass.
        raise ValueError("projection totals are not finite")
    if prior != "pass" or not projections:
        return prior, None, t
    if not any(p.quantified for p in projections):
        return "not_evaluated", "nothing quantifiable", t
    if t.net >= float(gate_cfg["ack_kg_co2e_yr"]):
        return "ack_required", None, t
    if t.net >= float(gate_cfg["warn_kg_co2e_yr"]):
        return "pass_with_warning", None, t
    return "pass", None, t


def conclusion(status: str, gate_cfg: dict) -> str:
    """Check conclusion for a status: success, failure or neutral.

    "not evaluated" follows `policy.yaml -> gate.not_evaluated_conclusion`. A missing key fails
    closed, because GitHub counts `neutral` as passing a required check; an unknown value raises.
    """
    if status != "not_evaluated":
        return CONCLUSIONS[status]
    value = gate_cfg.get("not_evaluated_conclusion", "failure")
    if value not in NOT_EVALUATED_CONCLUSIONS:
        raise ValueError(f"gate.not_evaluated_conclusion must be neutral or failure, got {value!r}")
    return str(value)
