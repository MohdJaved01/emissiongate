"""Quantifier: kWh and kgCO2e per resource with provenance; one ledger event per figure."""

from __future__ import annotations

from emissiongate.agents.context import RunContext
from emissiongate.contracts import EmissionRecord
from emissiongate.core import energy
from emissiongate.core.factors import FactorNotFound
from emissiongate.core.interventions import ResourceFacts, footprint


def quantify(
    ctx: RunContext, facts: list[ResourceFacts]
) -> tuple[dict[str, EmissionRecord], list[tuple[str, str]]]:
    records: dict[str, EmissionRecord] = {}
    not_quantified: list[tuple[str, str]] = []
    for f in facts:
        rid = f.resource.resource_id
        try:
            fp = footprint(f, ctx.factors)
        except (FactorNotFound, ValueError) as exc:
            not_quantified.append((rid, str(exc)))
            ctx.ledger.append(
                state=ctx.state,
                kind="error",
                agent="quantifier",
                detail={"resource_id": rid, "reason": str(exc)[:300]},
            )
            continue
        event = ctx.ledger.append(
            state=ctx.state,
            kind="decision",
            agent="quantifier",
            payload={
                "resource": f.resource.model_dump(),
                "utilisation": f.util.model_dump(exclude={"active_mask_168"}),
                "instance_hours_yr": f.instance_hours_yr,
                "kwh_yr": fp.kwh_yr,
                "kg_co2e_yr": fp.kg_co2e_yr,
                "provenance": [p.model_dump(mode="json") for p in fp.provenance],
            },
            detail={
                "resource_id": rid,
                "kwh_yr": fp.kwh_yr,
                "kg_co2e_yr": fp.kg_co2e_yr,
                "tier": "annual",
                "factors": ctx.factors.source,
            },
        )
        records[rid] = energy.emission_record(
            rid,
            fp.kwh_yr,
            ctx.factors.region_g_per_kwh(f.resource.region),
            fp.pue,
            fp.breakdown,
            fp.provenance,
            event.seq,
        )
    return records, not_quantified
