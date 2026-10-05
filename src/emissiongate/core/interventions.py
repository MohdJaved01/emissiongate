"""Quantification and intervention valuation (METHODOLOGY §1–§3, INTERVENTIONS).

For each template: eligibility, allowed parameter values, the rule-based default and the savings
function. Savings are always recomputed here from the chosen parameters, so a decision (rule or LLM)
can only pick among allowed values; it never supplies a number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from emissiongate.contracts import (
    EnergyBreakdown,
    Intervention,
    ParamOption,
    Provenance,
    Resource,
    Utilisation,
)
from emissiongate.core import energy
from emissiongate.core.factors import Factors, InstanceSpec
from emissiongate.core.grid import GridSnapshot
from emissiongate.core.regions import region_time_zone

HOURS_PER_YEAR = 8760.0
HOURS_PER_WEEK = 168
MONTHS_PER_YEAR = 12
GB_PER_TB = 1000  # decimal TB, as in METHODOLOGY G4
DAY_NAMES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


@dataclass(frozen=True)
class Prices:
    """Synthetic list prices from the estate generator (labelled synthetic everywhere)."""

    instance_usd_per_hour: dict[str, float]
    storage_usd_per_gb_month: dict[str, float]

    @classmethod
    def from_doc(cls, doc: dict) -> Prices:
        if doc.get("synthetic") is not True:
            raise ValueError("prices file must be labelled synthetic")
        return cls(
            dict(doc["instance_usd_per_hour_synthetic"]),
            dict(doc["storage_usd_per_gb_month_synthetic"]),
        )

    def instance(self, instance_type: str) -> float:
        if instance_type not in self.instance_usd_per_hour:
            raise KeyError(f"no synthetic price for {instance_type}")
        return self.instance_usd_per_hour[instance_type]

    def storage(self, storage_class: str) -> float:
        if storage_class not in self.storage_usd_per_gb_month:
            raise KeyError(f"no synthetic price for storage class {storage_class}")
        return self.storage_usd_per_gb_month[storage_class]


@dataclass(frozen=True)
class ResourceFacts:
    resource: Resource
    util: Utilisation
    instance_hours_yr: float | None = None  # compute only: instance-hours per year
    cost_usd_synthetic_yr: float = 0.0
    meta: dict = field(default_factory=dict)  # attached, unattached_days, lifecycle, schedules


@dataclass(frozen=True)
class Footprint:
    resource_id: str
    kwh_yr: float
    kg_co2e_yr: float
    g_per_kwh: float
    pue: float
    breakdown: EnergyBreakdown
    provenance: tuple[Provenance, ...]


@dataclass(frozen=True)
class Valuation:
    resource_id: str
    intervention: Intervention
    params: dict[str, str]
    kwh_saved_yr: float
    kg_co2e_saved_yr: float
    usd_synthetic_saved_yr: float
    kg_co2e_before_yr: float
    kg_co2e_after_yr: float
    confidence: str
    provenance: tuple[Provenance, ...]
    notes: tuple[str, ...] = ()


# ---- footprint ----------------------------------------------------------------------------------


def _u(value: float | None, name: str, resource_id: str) -> float:
    if value is None:
        raise ValueError(f"{resource_id}: {name} unknown; cannot quantify")
    return value


def _compute_energy(
    facts: ResourceFacts, factors: Factors, instance_type: str, u_cpu: float, hours: float
) -> energy.ComputeEnergy:
    spec = factors.instance(instance_type).value
    u_gpu = None
    if spec.gpu_count:
        u_gpu = _u(facts.util.gpu_avg, "gpu_avg", facts.resource.resource_id)
    return energy.compute(factors, instance_type, u_cpu, u_gpu, hours=hours)


def footprint(facts: ResourceFacts, factors: Factors) -> Footprint:
    r = facts.resource
    intensity = factors.region_g_per_kwh(r.region)
    if r.kind in ("ebs", "s3"):
        if r.storage_tb is None or r.storage_class is None:
            raise ValueError(f"{r.resource_id}: storage size or class unknown")
        s = energy.storage(factors, r.storage_tb, r.storage_class)
        breakdown = EnergyBreakdown(
            cpu_watts=0.0, gpu_watts=0.0, memory_watts=0.0, storage_kwh_yr=s.kwh
        )
        kwh, pue, prov = s.kwh, s.pue, s.provenance
    else:
        if r.instance_type is None or facts.instance_hours_yr is None:
            raise ValueError(f"{r.resource_id}: instance type or hours unknown")
        u_cpu = _u(facts.util.cpu_avg, "cpu_avg", r.resource_id)
        e = _compute_energy(facts, factors, r.instance_type, u_cpu, facts.instance_hours_yr)
        breakdown = EnergyBreakdown(
            cpu_watts=e.cpu_watts * r.count,
            gpu_watts=e.gpu_watts * r.count,
            memory_watts=e.memory_watts * r.count,
        )
        kwh, pue, prov = e.kwh, e.pue, e.provenance
    return Footprint(
        resource_id=r.resource_id,
        kwh_yr=kwh,
        kg_co2e_yr=energy.kg_co2e(kwh, intensity.value),
        g_per_kwh=intensity.value,
        pue=pue,
        breakdown=breakdown,
        provenance=(*prov, intensity.provenance),
    )


# ---- rightsize and graviton ---------------------------------------------------------------------


def _same_family_smaller(factors: Factors, spec: InstanceSpec) -> list[InstanceSpec]:
    out = []
    for t in factors.instance_types():
        s = factors.instance(t).value
        same_shape = s.family == spec.family and s.arch == spec.arch
        same_gpu = s.gpu == spec.gpu and s.gpu_count == spec.gpu_count
        if same_shape and same_gpu and s.vcpu < spec.vcpu:
            out.append(s)
    return sorted(out, key=lambda s: s.vcpu)


def rightsize_options(facts: ResourceFacts, factors: Factors, max_p95: float) -> list[str]:
    r = facts.resource
    if r.kind not in ("ec2_asg", "rds") or not r.instance_type or not facts.util.sufficient:
        return []
    if facts.util.cpu_p95 is None:
        return []
    spec = factors.instance(r.instance_type).value
    allowed = []
    for s in _same_family_smaller(factors, spec):
        projected_p95 = facts.util.cpu_p95 * spec.vcpu / s.vcpu
        if projected_p95 <= max_p95:
            allowed.append(s.instance_type)
    return allowed  # smallest first: the rule-based default is allowed[0]


def _type_change_value(
    facts: ResourceFacts,
    factors: Factors,
    prices: Prices,
    intervention: Intervention,
    target: str,
    confidence: str,
    notes: tuple[str, ...],
) -> Valuation:
    r = facts.resource
    assert r.instance_type and facts.instance_hours_yr is not None
    old = factors.instance(r.instance_type).value
    new = factors.instance(target).value
    u = _u(facts.util.cpu_avg, "cpu_avg", r.resource_id)
    u_new = min(1.0, u * old.vcpu / new.vcpu) if intervention == "rightsize" else u
    hours = facts.instance_hours_yr
    before = _compute_energy(facts, factors, r.instance_type, u, hours)
    after = _compute_energy(facts, factors, target, u_new, hours)
    intensity = factors.region_g_per_kwh(r.region)
    kwh_saved = before.kwh - after.kwh
    usd = (prices.instance(r.instance_type) - prices.instance(target)) * hours
    return Valuation(
        resource_id=r.resource_id,
        intervention=intervention,
        params={"target_instance_type": target}
        | ({"image_param": "ami_arm64"} if intervention == "graviton" else {}),
        kwh_saved_yr=kwh_saved,
        kg_co2e_saved_yr=energy.kg_co2e(kwh_saved, intensity.value),
        usd_synthetic_saved_yr=usd,
        kg_co2e_before_yr=energy.kg_co2e(before.kwh, intensity.value),
        kg_co2e_after_yr=energy.kg_co2e(after.kwh, intensity.value),
        confidence=confidence,
        provenance=(*before.provenance, intensity.provenance),
        notes=notes,
    )


def value_rightsize(
    facts: ResourceFacts, factors: Factors, prices: Prices, target: str
) -> Valuation:
    gpu = bool(factors.instance(target).value.gpu_count)
    notes = ("GPU utilisation held constant (EG-simplification-3).",) if gpu else ()
    return _type_change_value(
        facts, factors, prices, "rightsize", target, "medium" if gpu else "high", notes
    )


def graviton_options(facts: ResourceFacts, factors: Factors) -> list[str]:
    r = facts.resource
    if r.kind != "ec2_asg" or not r.instance_type or not facts.util.sufficient:
        return []
    spec = factors.instance(r.instance_type).value
    if spec.arch != "x86_64" or spec.gpu_count:
        return []
    cls_letter = spec.family[0]
    out = []
    for t in factors.instance_types():
        s = factors.instance(t).value
        if s.arch == "arm64" and s.family[0] == cls_letter and s.size == spec.size:
            out.append(s)

    def generation(s: InstanceSpec) -> int:
        m = re.search(r"(\d+)", s.family)
        return int(m.group(1)) if m else 0

    return [s.instance_type for s in sorted(out, key=generation, reverse=True)]


def value_graviton(
    facts: ResourceFacts, factors: Factors, prices: Prices, target: str
) -> Valuation:
    notes = (
        "Equal work per vCPU assumed (EG-simplification-2).",
        "Requires an arm64 build of the workload.",
    )
    return _type_change_value(facts, factors, prices, "graviton", target, "medium", notes)


# ---- schedule -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduleShape:
    days: tuple[int, ...]  # local weekdays, Monday = 0
    on_hour: int  # local
    off_hour: int  # local, exclusive
    time_zone: str

    @property
    def day_spec(self) -> str:
        if self.days == (0, 1, 2, 3, 4):
            return "MON-FRI"
        return ",".join(DAY_NAMES[d] for d in self.days)


def schedule_shape(util: Utilisation, region: str, reference: datetime) -> ScheduleShape | None:
    """Derive local on/off hours from the UTC activity mask, or None if it is not one daily span."""
    mask = util.active_mask_168
    if not mask or not any(mask):
        return None
    tz_name = region_time_zone(region)
    offset = reference.astimezone(ZoneInfo(tz_name)).utcoffset() or timedelta(0)
    shift = int(offset.total_seconds() // 3600)
    local = [False] * HOURS_PER_WEEK
    for k, active in enumerate(mask):
        local[(k + shift) % HOURS_PER_WEEK] = active
    days, firsts, lasts = [], [], []
    for d in range(7):
        hours = [h for h in range(24) if local[d * 24 + h]]
        if not hours:
            continue
        if hours != list(range(hours[0], hours[-1] + 1)):
            return None  # not one contiguous span per day
        days.append(d)
        firsts.append(hours[0])
        lasts.append(hours[-1])
    if len(set(firsts)) != 1 or len(set(lasts)) != 1 or lasts[0] + 1 >= 24:
        return None
    return ScheduleShape(tuple(days), firsts[0], lasts[0] + 1, tz_name)


def schedule_eligible(facts: ResourceFacts, thresholds: dict) -> tuple[bool, str]:
    u = facts.util
    if facts.resource.kind != "ec2_asg":
        return False, "schedule applies to autoscaling groups only"
    if facts.meta.get("schedules"):
        return False, "already scheduled"
    if not u.sufficient or u.active_hour_share is None:
        return False, "insufficient utilisation evidence"
    if u.active_hour_share >= thresholds["schedule_max_active_share"]:
        return False, f"active {u.active_hour_share:.0%} of the week"
    if (u.weekly_regularity or 0.0) < thresholds["weekly_pattern_min_regularity"]:
        return False, "activity is not a regular weekly pattern"
    if (u.mask_coverage or 0.0) < thresholds["schedule_min_mask_coverage"]:
        return False, "activity falls outside any weekly mask (not a weekly pattern)"
    return True, ""


def schedule_options(shape: ScheduleShape, count: int) -> list[ParamOption]:
    spec = shape.day_spec
    on_exact = f"0 {shape.on_hour} * * {spec}"
    off_exact = f"0 {shape.off_hour} * * {spec}"
    on_padded = f"30 {shape.on_hour - 1} * * {spec}" if shape.on_hour > 0 else on_exact
    off_padded = f"30 {shape.off_hour} * * {spec}" if shape.off_hour < 23 else off_exact
    return [
        ParamOption(name="on_cron", allowed=sorted({on_exact, on_padded}, key=on_exact.__ne__)),
        ParamOption(name="off_cron", allowed=sorted({off_exact, off_padded}, key=off_exact.__ne__)),
        ParamOption(name="time_zone", allowed=[shape.time_zone]),
        ParamOption(name="min_on", allowed=[str(count)]),
    ]


def _cron_minutes(cron: str) -> tuple[int, int, str]:
    minute, hour, _, _, days = cron.split()
    return int(hour) * 60 + int(minute), len(_expand_days(days)), days


def _expand_days(spec: str) -> list[int]:
    if spec == "*":
        return list(range(7))
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = (DAY_NAMES.index(x) for x in part.split("-"))
            out.extend(range(a, b + 1))
        else:
            out.append(DAY_NAMES.index(part))
    return sorted(set(out))


def on_hours_per_week(on_cron: str, off_cron: str) -> float:
    on_min, n_days, on_days = _cron_minutes(on_cron)
    off_min, _, off_days = _cron_minutes(off_cron)
    if on_days != off_days or off_min <= on_min:
        raise ValueError("on/off recurrences must share days and off must follow on")
    return n_days * (off_min - on_min) / 60.0


def value_schedule(
    facts: ResourceFacts, factors: Factors, prices: Prices, params: dict[str, str]
) -> Valuation:
    r = facts.resource
    assert r.instance_type and facts.instance_hours_yr is not None
    on_week = on_hours_per_week(params["on_cron"], params["off_cron"])
    removed_share = (HOURS_PER_WEEK - on_week) / HOURS_PER_WEEK
    removed_hours = facts.instance_hours_yr * removed_share
    u_off = _u(facts.util.cpu_avg_off_mask, "cpu_avg_off_mask", r.resource_id)
    spec = factors.instance(r.instance_type).value
    u_gpu_off = None
    if spec.gpu_count:
        u_gpu_off = _u(facts.util.gpu_avg_off_mask, "gpu_avg_off_mask", r.resource_id)
    removed = energy.compute(factors, r.instance_type, u_off, u_gpu_off, hours=removed_hours)
    before = footprint(facts, factors)
    intensity = factors.region_g_per_kwh(r.region)
    kg_saved = energy.kg_co2e(removed.kwh, intensity.value)
    return Valuation(
        resource_id=r.resource_id,
        intervention="schedule",
        params=dict(params),
        kwh_saved_yr=removed.kwh,
        kg_co2e_saved_yr=kg_saved,
        usd_synthetic_saved_yr=prices.instance(r.instance_type) * removed_hours,
        kg_co2e_before_yr=before.kg_co2e_yr,
        kg_co2e_after_yr=before.kg_co2e_yr - kg_saved,
        confidence="high" if (facts.util.weekly_regularity or 0) >= 0.95 else "medium",
        provenance=before.provenance,
        notes=(
            f"On {on_week:g} h/week; scaled to zero outside the schedule.",
            "Cold start: the first request after scale-up waits for instances to boot.",
        ),
    )


# ---- storage_tier -------------------------------------------------------------------------------

STORAGE_TIER_DAYS = ("90", "30", "180")
STORAGE_TIER_CLASSES = ("GLACIER_IR", "DEEP_ARCHIVE")


def value_storage_tier(
    facts: ResourceFacts, factors: Factors, prices: Prices, params: dict[str, str]
) -> Valuation:
    r = facts.resource
    assert r.storage_tb is not None and r.storage_class is not None
    target = params["storage_class"]
    before = energy.storage(factors, r.storage_tb, r.storage_class)
    after = energy.storage(factors, r.storage_tb, target)
    intensity = factors.region_g_per_kwh(r.region)
    gb = r.storage_tb * GB_PER_TB
    usd = gb * (prices.storage(r.storage_class) - prices.storage(target)) * MONTHS_PER_YEAR
    kwh_saved = before.kwh - after.kwh
    return Valuation(
        resource_id=r.resource_id,
        intervention="storage_tier",
        params=dict(params),
        kwh_saved_yr=kwh_saved,
        kg_co2e_saved_yr=energy.kg_co2e(kwh_saved, intensity.value),
        usd_synthetic_saved_yr=usd,
        kg_co2e_before_yr=energy.kg_co2e(before.kwh, intensity.value),
        kg_co2e_after_yr=energy.kg_co2e(after.kwh, intensity.value),
        confidence="high",
        provenance=(*before.provenance, intensity.provenance),
        notes=(
            "Under CCF both classes use the HDD coefficient: ~0 kWh saved (METHODOLOGY §3).",
            "Cost saving assumes all objects are older than the transition (synthetic prices).",
            "Transition only; no expiration block.",
        ),
    )


# ---- time_shift ---------------------------------------------------------------------------------


def _window_mean(slot_means: dict[int, float], start_slot: int, n_slots: int) -> float:
    return sum(slot_means[(start_slot + i) % 48] for i in range(n_slots)) / n_slots


def time_shift_options(
    facts: ResourceFacts,
    snapshot: GridSnapshot,
    allowed_window: str,
    reference: datetime,
) -> tuple[list[str], dict[str, float], str]:
    """Start crons within the allowed local window, best (lowest mean intensity) first."""
    sched = facts.meta.get("schedules") or {}
    up, down = sched.get("up"), sched.get("down")
    if not up or not down:
        return [], {}, ""
    tz = ZoneInfo(sched.get("time_zone") or region_time_zone(facts.resource.region))
    offset_h = (reference.astimezone(tz).utcoffset() or timedelta(0)).total_seconds() / 3600
    up_m, _, _ = _cron_minutes(up + " *" if len(up.split()) == 4 else up)
    down_m, _, _ = _cron_minutes(down + " *" if len(down.split()) == 4 else down)
    duration = down_m - up_m
    n_slots = duration // 30
    means = snapshot.mean_by_slot_of_day()

    def to_utc_slot(local_minutes: int) -> int:
        return int(((local_minutes - offset_h * 60) % 1440) // 30)

    lo, hi = allowed_window.split("-")
    lo_m = int(lo[:2]) * 60 + int(lo[3:])
    hi_m = int(hi[:2]) * 60 + int(hi[3:])
    scored: dict[str, float] = {}
    for start in range(lo_m, hi_m - duration + 1, 30):
        cron = f"{start % 60} {start // 60} * * *"
        scored[cron] = _window_mean(means, to_utc_slot(start), n_slots)
    current = f"{up_m % 60} {up_m // 60} * * *"
    scored.setdefault(current, _window_mean(means, to_utc_slot(up_m), n_slots))
    ranked = sorted(scored, key=lambda c: (scored[c], c))
    return ranked, scored, current


def value_time_shift(
    facts: ResourceFacts,
    factors: Factors,
    snapshot: GridSnapshot,
    scored: dict[str, float],
    current: str,
    start_cron: str,
) -> Valuation:
    before = footprint(facts, factors)
    i_now, i_new = scored[current], scored[start_cron]
    kg_saved = before.kwh_yr * (i_now - i_new) / 1000.0
    return Valuation(
        resource_id=facts.resource.resource_id,
        intervention="time_shift",
        params={"start_cron": start_cron},
        kwh_saved_yr=0.0,
        kg_co2e_saved_yr=kg_saved,
        usd_synthetic_saved_yr=0.0,
        kg_co2e_before_yr=before.kwh_yr * i_now / 1000.0,
        kg_co2e_after_yr=before.kwh_yr * i_new / 1000.0,
        confidence="medium",
        provenance=(*before.provenance[:-1], snapshot.provenance),
        notes=(
            f"7-day mean intensity: {i_now:.1f} g/kWh now vs {i_new:.1f} g/kWh in the new "
            f"window (tier snapshot, {snapshot.provenance.source}).",
            "kWh unchanged; only the grid intensity of the hours used changes.",
        ),
    )
