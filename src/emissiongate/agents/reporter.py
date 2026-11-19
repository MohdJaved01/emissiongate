"""Reporter (gate): the sticky PR comment. Numbers from core; wording from the template only."""

from __future__ import annotations

from emissiongate.contracts import GateResult, Projection, ResourceChange
from emissiongate.core.factors import Factors
from emissiongate.report.render import published_delta, render_markdown
from emissiongate.report.sanitize import checked
from emissiongate.tools.github import MARKER

STATUS = {
    "pass": ("✅", "pass"),
    "pass_with_warning": ("⚠️", "pass, with a warning"),
    "ack_required": ("❌", "carbon acknowledgement required"),
    "accepted": ("✅", "increase accepted by a human"),
    "not_evaluated": ("⚪", "not evaluated"),
}


def _hours(text: str | None) -> str:
    if text is None:
        return "?"
    try:
        h = float(text)
    except ValueError:
        return text
    return "24×7" if abs(h - 8760.0) < 0.5 else f"{h:,.0f} h/yr"


_KINDS = {
    "instance_type": "instance_type",
    "region": "region",
    "count": "number",
    "size_gb": "number",
    "hours_per_year": "number",
    "type": "volume_type",
}


def _checked(attrs: dict[str, str]) -> dict[str, str]:
    """Plan attribute values in their expected formats, for display (THREAT_MODEL B5)."""
    return {k: checked(_KINDS[k], v) if k in _KINDS else v for k, v in attrs.items()}


def describe(c: ResourceChange) -> str:
    a, b = _checked(c.after), _checked(c.before)
    if c.change == "added":
        if "instance_type" in a:
            hours = _hours(a.get("hours_per_year"))
            return f"added: {a['count']} × {a['instance_type']}, {a['region']}, {hours}"
        size = f"{a.get('size_gb', '?')} GB {a.get('type', '')}"
        return f"added: {a.get('count', '1')} × {size}, {a['region']}"
    if c.change == "removed":
        if "instance_type" in b:
            return f"removed: {b['count']} × {b['instance_type']}, {b['region']}"
        return f"removed: {b.get('count', '1')} × {b.get('size_gb', '?')} GB, {b['region']}"
    parts = []
    labels = {
        "count": "count",
        "instance_type": "type",
        "region": "region",
        "size_gb": "size GB",
        "type": "volume type",
    }
    for key, label in labels.items():
        if b.get(key) != a.get(key):
            parts.append(f"{label} {b.get(key)} → {a.get(key)}")
    if b.get("hours_per_year") != a.get("hours_per_year"):
        parts.append(f"hours {_hours(b.get('hours_per_year'))} → {_hours(a.get('hours_per_year'))}")
    return "changed: " + ", ".join(parts)


def basis(p: Projection, gate_cfg: dict, factors: Factors, lookback_days: int) -> str:
    if p.address.startswith("aws_ebs_volume."):
        return "configuration (storage size and class; no utilisation needed)"
    if p.basis == "assumed":
        lo, hi = gate_cfg["assumed_utilisation_band"]
        cpu = factors.constant("default_cpu_utilization").value
        gpu = gate_cfg["assumed_gpu_utilisation"]
        return (
            f"**assumed** (no telemetry): CPU {cpu:.0%} (CCF default), GPU {gpu:.0%}; "
            f"range {lo:.0%}–{hi:.0%}"
        )
    if p.basis == "observed_projected":
        return "observed, projected (total work held constant)"
    return f"observed ({lookback_days}-day telemetry)"


def gate_comment(
    result: GateResult,
    gate_cfg: dict,
    factors: Factors,
    lookback_days: int,
    runtime_s: float,
    energy_wh: float | None,
    energy_label: str | None,
    reason: str | None,
    notes: list[str] | None = None,
) -> str:
    icon, label = STATUS[result.status]
    by_addr = {p.address: p for p in result.projections}
    rows = []
    for c in result.changes:
        if not c.carbon_relevant:
            continue
        p = by_addr.get(c.address)
        if p is None or not p.quantified:
            continue
        delta = published_delta(p.kg_co2e_yr_before, p.kg_co2e_yr_after)
        rows.append(
            {
                "address": c.address,
                "what": describe(c),
                "basis": basis(p, gate_cfg, factors, lookback_days),
                "p": p,
                "delta": delta,
            }
        )
    not_quantified = [p for p in result.projections if not p.quantified]
    other = [c for c in result.changes if not c.carbon_relevant and c.change != "unchanged"]
    assumed = any(p.basis == "assumed" and p.quantified for p in result.projections)
    kwh = sum(p.kwh_yr_delta for p in result.projections if p.quantified)
    usd = sum(p.usd_synthetic_yr_delta for p in result.projections if p.quantified)
    net = sum(r["delta"] for r in rows)
    seen = sum(1 for c in result.changes if c.change != "unchanged")
    return render_markdown(
        "gate_comment.md.j2",
        marker=MARKER,
        icon=icon,
        label=label,
        r=result,
        net=net,
        assumed=assumed,
        kwh=kwh,
        usd=usd,
        rows=rows,
        suggestions=result.suggestions,
        not_quantified=not_quantified,
        other=other,
        seen=seen,
        gate=gate_cfg,
        reason=reason,
        factors_source=factors.source,
        runtime_s=runtime_s,
        energy_wh=energy_wh,
        energy_label=energy_label,
        notes=notes or [],
    )
