"""time_shift: move the recurrences of an existing scale-up/scale-down pair."""

from __future__ import annotations

from emissiongate.contracts import Resource
from emissiongate.core.hcl import get_attribute, q, set_attribute
from emissiongate.core.patches._common import tf_name


def _minutes(cron: str) -> int:
    minute, hour = cron.split()[:2]
    return int(hour) * 60 + int(minute)


def render(resource: Resource, text: str, params: dict[str, str], inject_bad: bool) -> str:
    name = tf_name(resource)
    up = ("aws_autoscaling_schedule", f"{name}_up")
    down = ("aws_autoscaling_schedule", f"{name}_down")
    old_up = (get_attribute(text, "resource", up, "recurrence") or "").strip('"')
    old_down = (get_attribute(text, "resource", down, "recurrence") or "").strip('"')
    if not old_up or not old_down:
        raise ValueError(f"{name}: no scale-up/scale-down schedule pair to move")
    duration = _minutes(old_down) - _minutes(old_up)
    start = _minutes(params["start_cron"])
    end = start + duration
    rest = " ".join(params["start_cron"].split()[2:])
    text = set_attribute(text, "resource", up, "recurrence", q(params["start_cron"]))
    return set_attribute(text, "resource", down, "recurrence", q(f"{end % 60} {end // 60} {rest}"))
