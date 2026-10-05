"""Diff Collector (gate): pair base/head plan JSON by address; extract carbon-relevant attributes.

GATE §3: launch template + ASG (instance_type, desired_capacity, region from the provider),
autoscaling schedules (hours on), aws_instance, aws_db_instance, aws_ebs_volume. Everything else is
listed as not carbon-relevant. Tags-only changes are not carbon-relevant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from emissiongate.contracts import ResourceChange
from emissiongate.core.projection import hours_per_year

COMPUTE_TYPES = ("aws_autoscaling_group", "aws_instance", "aws_db_instance")
STORAGE_TYPES = ("aws_ebs_volume",)
HELPER_TYPES = ("aws_launch_template", "aws_autoscaling_schedule")
INDEX = re.compile(r"\[[^\]]*\]$")


@dataclass(frozen=True)
class Unit:
    address: str
    tf_type: str
    name: str
    region: str | None
    instance_type: str | None = None
    count: int = 1
    hours_per_year: float = 8760.0
    schedules: tuple[tuple[str, str, int], ...] = ()
    tags: dict[str, str] = field(default_factory=dict)
    storage_gb: float | None = None
    storage_type: str | None = None
    missing: tuple[str, ...] = ()  # attributes the plan did not resolve: never defaulted

    def attrs(self) -> dict[str, str]:
        out = {"region": self.region or "unknown"}
        if self.instance_type:
            out |= {
                "instance_type": self.instance_type,
                "count": str(self.count),
                "hours_per_year": f"{self.hours_per_year:.1f}",
            }
        if self.storage_gb is not None:
            out |= {
                "size_gb": f"{self.storage_gb:g}",
                "type": self.storage_type or "?",
                "count": str(self.count),
            }
        return out


@dataclass
class PlanView:
    units: dict[str, Unit]
    other: dict[str, dict]  # address -> values, for non-carbon-relevant resources


def _region(plan: dict, provider_key: str | None) -> str | None:
    cfg = plan.get("configuration", {}).get("provider_config", {})
    entry = cfg.get(provider_key or "aws") or cfg.get("aws") or {}
    region = entry.get("expressions", {}).get("region", {})
    return region.get("constant_value")


def _refs(expr: object) -> list[str]:
    if isinstance(expr, list):
        expr = expr[0] if expr else {}
    if not isinstance(expr, dict):
        return []
    out: list[str] = []
    for value in expr.values():
        if isinstance(value, dict):
            out.extend(value.get("references", []))
    return out


def _tags(values: dict) -> dict[str, str]:
    if isinstance(values.get("tag"), list):
        return {t["key"]: str(t["value"]) for t in values["tag"]}
    tags = values.get("tags") or {}
    return {str(k): str(v) for k, v in tags.items()}


def read_plan(plan: dict) -> PlanView:
    resources = plan.get("planned_values", {}).get("root_module", {}).get("resources", [])
    config = {
        r["address"]: r
        for r in plan.get("configuration", {}).get("root_module", {}).get("resources", [])
    }
    by_base: dict[str, list[dict]] = {}
    for r in resources:
        by_base.setdefault(INDEX.sub("", r["address"]), []).append(r)

    templates = {a: rs[0]["values"] for a, rs in by_base.items() if a.startswith(HELPER_TYPES[0])}
    schedules: dict[str, list[tuple[str, str, int]]] = {}
    for addr, rs in by_base.items():
        if not addr.startswith("aws_autoscaling_schedule."):
            continue
        refs = [x for x in _refs(config.get(addr, {}).get("expressions", {})) if x.count(".") == 1]
        asg = next((x for x in refs if x.startswith("aws_autoscaling_group.")), None)
        v = rs[0]["values"]
        if asg:
            schedules.setdefault(asg, []).append(
                (
                    str(v.get("recurrence")),
                    str(v.get("time_zone")),
                    -1 if v.get("desired_capacity") is None else int(v["desired_capacity"]),
                )
            )

    units: dict[str, Unit] = {}
    other: dict[str, dict] = {}
    for addr, rs in by_base.items():
        tf_type, name = addr.split(".", 1)
        values = rs[0]["values"]
        region = _region(plan, config.get(addr, {}).get("provider_config_key"))
        if tf_type == "aws_autoscaling_group":
            lt_refs = _refs(config.get(addr, {}).get("expressions", {}).get("launch_template"))
            lt = next((x for x in lt_refs if x.count(".") == 1), None)
            itype = templates.get(lt or "", {}).get("instance_type")
            sched = tuple(sorted(schedules.get(addr, [])))
            desired = values.get("desired_capacity")
            missing = tuple(
                k for k, v in (("instance_type", itype), ("desired_capacity", desired)) if v is None
            )
            try:
                hours = hours_per_year(list(sched))
                if any(s[2] < 0 for s in sched):
                    raise ValueError("schedule capacity unknown")
            except ValueError:
                hours, missing = 8760.0, (*missing, "schedule")
            units[addr] = Unit(
                address=addr,
                tf_type=tf_type,
                name=name,
                region=region,
                instance_type=itype,
                count=int(desired) if desired is not None else 0,
                missing=missing,
                hours_per_year=hours,
                schedules=sched,
                tags=_tags(values),
            )
        elif tf_type == "aws_instance":
            units[addr] = Unit(
                addr,
                tf_type,
                name,
                region,
                values.get("instance_type"),
                len(rs),
                tags=_tags(values),
            )
        elif tf_type == "aws_db_instance":
            units[addr] = Unit(
                addr, tf_type, name, region, values.get("instance_class"), 1, tags=_tags(values)
            )
        elif tf_type in STORAGE_TYPES:
            units[addr] = Unit(
                addr,
                tf_type,
                name,
                region,
                count=len(rs),
                storage_gb=float(values["size"]) if values.get("size") is not None else None,
                storage_type=values.get("type"),
                tags=_tags(values),
                missing=tuple(k for k in ("size", "type") if values.get(k) is None),
            )
        elif tf_type not in HELPER_TYPES:
            other[addr] = values
    return PlanView(units, other)


def pair(base: PlanView, head: PlanView) -> list[ResourceChange]:
    changes: list[ResourceChange] = []
    for addr in sorted(set(base.units) | set(head.units)):
        b, h = base.units.get(addr), head.units.get(addr)
        if b is None:
            changes.append(
                ResourceChange(address=addr, change="added", carbon_relevant=True, after=h.attrs())
            )  # type: ignore[union-attr]
        elif h is None:
            changes.append(
                ResourceChange(
                    address=addr, change="removed", carbon_relevant=True, before=b.attrs()
                )
            )
        else:
            relevant = b.attrs() != h.attrs()
            changes.append(
                ResourceChange(
                    address=addr,
                    change="changed" if relevant or b.tags != h.tags else "unchanged",
                    carbon_relevant=relevant,
                    before=b.attrs(),
                    after=h.attrs(),
                )
            )
    for addr in sorted(set(base.other) | set(head.other)):
        if base.other.get(addr) != head.other.get(addr):
            kind = (
                "added"
                if addr not in base.other
                else ("removed" if addr not in head.other else "changed")
            )
            changes.append(ResourceChange(address=addr, change=kind, carbon_relevant=False))
    return changes
