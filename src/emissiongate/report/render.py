"""Rendering: PR bodies (markdown) and the run report (HTML). Rounding happens here only.

Every number comes from core/; LLM prose enters through one `narrative` slot (invariant 1).
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

TEMPLATES = Path(__file__).parent / "templates"
MINUS = "−"


def kg(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    text = f"{abs(value):,.{digits}f}"
    return f"{MINUS}{text}" if value < 0 and float(text.replace(",", "")) != 0 else text


def signed(value: float, digits: int = 1) -> str:
    text = f"{abs(value):,.{digits}f}"
    if float(text.replace(",", "")) == 0:
        return text
    return f"+{text}" if value > 0 else f"{MINUS}{text}"


def published_delta(before: float, after: float, digits: int = 1) -> float:
    """METHODOLOGY §6: publish the difference of the rounded before/after values."""
    return round(after, digits) - round(before, digits)


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def usd(value: float) -> str:
    return f"{value:,.0f}"


def env(autoescape: bool) -> Environment:
    e = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        undefined=StrictUndefined,
        autoescape=select_autoescape(["html"]) if autoescape else False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    e.filters.update(kg=kg, signed=signed, pct=pct, usd=usd)
    e.globals.update(published_delta=published_delta)
    return e


def render_markdown(template: str, **ctx: object) -> str:
    return env(False).get_template(template).render(**ctx)


def render_html(template: str, **ctx: object) -> str:
    return env(True).get_template(template).render(**ctx)


CHANGE_SUMMARY = {
    "schedule": (
        "Adds two `aws_autoscaling_schedule` resources next to the group: scale to 0 at "
        "`{off_cron}` and back to {min_on} at `{on_cron}` ({time_zone}). The group's own size is "
        "unchanged."
    ),
    "graviton": (
        "Moves the launch template from `{old_type}` to `{target_instance_type}` and the image to "
        "`var.{image_param}` (two lines)."
    ),
    "rightsize": "Changes the instance size from `{old_type}` to `{target_instance_type}`.",
    "storage_tier": (
        "Adds a lifecycle rule that transitions objects to `{storage_class}` after "
        "{transition_days} days. No expiration block."
    ),
    "time_shift": "Moves the scheduled run to start at `{start_cron}` (same duration).",
}

TEMPLATE_NARRATIVE = {
    "schedule": (
        "This group is busy only during a regular weekly window but runs around the clock. "
        "Scaling it to zero outside the observed window removes idle energy and leaves capacity "
        "unchanged while it is in use."
    ),
    "graviton": (
        "The workload runs steadily on x86 instances that have an arm64 equivalent of the same "
        "size. Graviton processors draw less power for the same vCPU count under the published "
        "coefficients."
    ),
    "rightsize": (
        "Observed CPU stays far below what the current size provides, even at its peak. A smaller "
        "size in the same family keeps projected peak utilisation inside the policy limit."
    ),
    "storage_tier": (
        "Objects are retained for compliance and rarely read. Tiering lowers storage cost; under "
        "the methodology it barely changes carbon."
    ),
    "time_shift": (
        "The batch is deferrable. Moving it to the lowest-intensity window of the night uses the "
        "same energy at a lower grid intensity."
    ),
}


def change_summary(template: str, params: dict[str, str], old_type: str | None) -> str:
    return CHANGE_SUMMARY[template].format(old_type=old_type or "?", **params)
