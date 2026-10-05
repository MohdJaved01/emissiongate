"""Rank candidates by carbon, report cost alongside (ADR-0010). Deterministic tie-breaks."""

from __future__ import annotations

from emissiongate.core.interventions import Valuation


def key(v: Valuation) -> str:
    return f"{v.resource_id}:{v.intervention}"


def rank(valuations: list[Valuation]) -> dict[str, tuple[int, int]]:
    """Return {candidate_id: (rank_carbon, rank_cost)}, 1 = largest saving."""
    by_carbon = sorted(valuations, key=lambda v: (-v.kg_co2e_saved_yr, key(v)))
    by_cost = sorted(valuations, key=lambda v: (-v.usd_synthetic_saved_yr, key(v)))
    carbon = {key(v): i + 1 for i, v in enumerate(by_carbon)}
    cost = {key(v): i + 1 for i, v in enumerate(by_cost)}
    return {k: (carbon[k], cost[k]) for k in sorted(carbon)}


def best_per_resource(valuations: list[Valuation]) -> list[Valuation]:
    """One deliverable per resource: the largest carbon saving (one PR per resource group)."""
    best: dict[str, Valuation] = {}
    for v in sorted(valuations, key=lambda v: (-v.kg_co2e_saved_yr, key(v))):
        best.setdefault(v.resource_id, v)
    return sorted(best.values(), key=lambda v: (-v.kg_co2e_saved_yr, key(v)))
