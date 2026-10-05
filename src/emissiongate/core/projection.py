"""Projections for proposed changes (METHODOLOGY §3b, GATE §4). Pure functions.

- existing resource with telemetry, unchanged shape: observed utilisation
- capacity change: u_new = min(1, u_old × count_old / count_new)   (total work held constant)
- instance type change: u_new = min(1, u_old × vcpu_old / vcpu_new)
- new resource without telemetry: CPU at CCF's default (0.50), GPU at the policy's assumed value,
  published as a central value plus the policy band (default 0.10–0.90): label `assumed`
- removed resource: its current energy becomes a negative delta
Hours come from autoscaling-schedule recurrences (24×7 when none). Totals use the annual tier.
"""

from __future__ import annotations

from dataclasses import dataclass

from emissiongate.contracts import Projection, Provenance
from emissiongate.core import energy
from emissiongate.core.factors import FactorNotFound, Factors

HOURS_PER_YEAR = 8760.0
HOURS_PER_WEEK = 168.0
DAY_NAMES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


@dataclass(frozen=True)
class UnitState:
    instance_type: str
    count: int
    region: str
    hours_per_year: float  # per instance


@dataclass(frozen=True)
class Observed:
    u_cpu: float
    u_gpu: float | None
    p95_cpu: float | None


@dataclass(frozen=True)
class Energy:
    kwh: float
    kg: float
    provenance: tuple[Provenance, ...]


def _day(token: str) -> int:
    """Cron day of week: MON..SUN or 0..7 (0 and 7 are Sunday). Anything else raises ValueError."""
    if token.upper() in DAY_NAMES:
        return DAY_NAMES.index(token.upper())
    if token.isdigit() and 0 <= int(token) <= 7:
        return (int(token) - 1) % 7
    raise ValueError(f"unsupported cron day-of-week {token!r}")


def _days(spec: str) -> int:
    if spec in ("*", "?"):
        return 7
    days: set[int] = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = (_day(x) for x in part.split("-", 1))
            days.update(range(a, b + 1) if a <= b else [*range(a, 7), *range(0, b + 1)])
        else:
            days.add(_day(part))
    return len(days)


def hours_per_year(schedules: list[tuple[str, str, int]]) -> float:
    """Instance hours per year from (recurrence, time_zone, desired_capacity) pairs; none = 24×7."""
    ups = [s for s in schedules if s[2] > 0]
    downs = [s for s in schedules if s[2] == 0]
    if not ups or not downs:
        return HOURS_PER_YEAR
    up_fields, dn_fields = ups[0][0].split(), downs[0][0].split()
    if len(up_fields) != 5 or len(dn_fields) != 5:
        raise ValueError(f"unsupported recurrence {ups[0][0]!r} / {downs[0][0]!r}")
    up_m, up_h, *_, up_days = up_fields
    dn_m, dn_h, *_, _ = dn_fields
    if not all(x.isdigit() for x in (up_m, up_h, dn_m, dn_h)):
        raise ValueError(f"unsupported recurrence {ups[0][0]!r} / {downs[0][0]!r}")
    minutes = (int(dn_h) * 60 + int(dn_m)) - (int(up_h) * 60 + int(up_m))
    if minutes <= 0:
        minutes += 24 * 60
    weekly = _days(up_days) * minutes / 60.0
    return weekly * HOURS_PER_YEAR / HOURS_PER_WEEK


def energy_kg(
    factors: Factors, state: UnitState, u_cpu: float, u_gpu: float | None = None
) -> Energy:
    spec = factors.instance(state.instance_type).value
    gpu = (u_gpu if u_gpu is not None else u_cpu) if spec.gpu_count else None
    e = energy.compute(
        factors, state.instance_type, u_cpu, gpu, hours=state.hours_per_year, count=state.count
    )
    intensity = factors.region_g_per_kwh(state.region)
    return Energy(
        e.kwh, energy.kg_co2e(e.kwh, intensity.value), (*e.provenance, intensity.provenance)
    )


def projected_u(before: UnitState | None, after: UnitState, obs: Observed) -> float:
    u = obs.u_cpu
    if before is None:
        return u
    if before.count != after.count and after.count > 0:
        u = min(1.0, u * before.count / after.count)
    if before.instance_type != after.instance_type:
        return u  # applied by the caller with factors (vCPU ratio)
    return u


def _type_ratio(factors: Factors, before: UnitState, after: UnitState) -> float:
    if before.instance_type == after.instance_type:
        return 1.0
    return (
        factors.instance(before.instance_type).value.vcpu
        / factors.instance(after.instance_type).value.vcpu
    )


def project(
    address: str,
    before: UnitState | None,
    after: UnitState | None,
    observed: Observed | None,
    factors: Factors,
    gate: dict,
    usd_per_hour: dict[str, float] | None = None,
) -> Projection:
    low_u, high_u = (float(x) for x in gate["assumed_utilisation_band"])
    try:
        if before is None and after is None:
            raise ValueError("nothing to project")
        if observed is None:
            central_cpu = factors.constant("default_cpu_utilization").value
            central_gpu = float(gate["assumed_gpu_utilisation"])
            b = energy_kg(factors, before, central_cpu, central_gpu) if before else None
            a = energy_kg(factors, after, central_cpu, central_gpu) if after else None
            lo = energy_kg(factors, after, low_u, low_u) if after else None
            hi = energy_kg(factors, after, high_u, high_u) if after else None
            b_lo = energy_kg(factors, before, low_u, low_u) if before else None
            b_hi = energy_kg(factors, before, high_u, high_u) if before else None
            prov = (a or b).provenance  # type: ignore[union-attr]
            return Projection(
                address=address,
                basis="assumed",
                kg_co2e_yr_before=b.kg if b else 0.0,
                kg_co2e_yr_after=a.kg if a else 0.0,
                kg_co2e_yr_after_low=lo.kg if lo else 0.0,
                kg_co2e_yr_after_high=hi.kg if hi else 0.0,
                kg_co2e_yr_before_low=b_lo.kg if b_lo else 0.0,
                kg_co2e_yr_before_high=b_hi.kg if b_hi else 0.0,
                kwh_yr_delta=(a.kwh if a else 0.0) - (b.kwh if b else 0.0),
                usd_synthetic_yr_delta=_usd(before, after, usd_per_hour),
                provenance=list(dict.fromkeys(prov)),
            )
        b = energy_kg(factors, before, observed.u_cpu, observed.u_gpu) if before else None
        a = None
        changed = before is None or after is None or before != after
        if after is not None:
            u = observed.u_cpu
            if before is not None:
                if before.count != after.count and after.count > 0:
                    u = min(1.0, u * before.count / after.count)
                u = min(1.0, u * _type_ratio(factors, before, after))
            a = energy_kg(factors, after, u, observed.u_gpu)
        shape_changed = (
            before is not None
            and after is not None
            and (before.count != after.count or before.instance_type != after.instance_type)
        )
        prov = (a or b).provenance  # type: ignore[union-attr]
        return Projection(
            address=address,
            basis="observed_projected" if shape_changed else "observed",
            kg_co2e_yr_before=b.kg if b else 0.0,
            kg_co2e_yr_after=a.kg if a else 0.0,
            kwh_yr_delta=(a.kwh if a else 0.0) - (b.kwh if b else 0.0),
            usd_synthetic_yr_delta=_usd(before, after, usd_per_hour) if changed else 0.0,
            provenance=list(dict.fromkeys(prov)),
        )
    except (FactorNotFound, ValueError) as exc:
        return Projection(
            address=address,
            basis="assumed" if observed is None else "observed",
            kg_co2e_yr_before=0.0,
            kg_co2e_yr_after=0.0,
            kwh_yr_delta=0.0,
            usd_synthetic_yr_delta=0.0,
            provenance=[],
            quantified=False,
            reason=str(exc),
        )


def _usd(
    before: UnitState | None, after: UnitState | None, prices: dict[str, float] | None
) -> float:
    if not prices:
        raise ValueError("no synthetic price table; cost delta cannot be computed")

    def cost(s: UnitState | None) -> float:
        if s is None:
            return 0.0
        if s.instance_type not in prices:
            raise ValueError(f"no synthetic price for {s.instance_type}")
        return prices[s.instance_type] * s.count * s.hours_per_year

    return cost(after) - cost(before)
