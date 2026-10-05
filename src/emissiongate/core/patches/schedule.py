"""schedule: add an off and an on aws_autoscaling_schedule next to the ASG; never resize the ASG."""

from __future__ import annotations

from emissiongate.contracts import Resource
from emissiongate.core.hcl import Attr, Block, get_attribute, q
from emissiongate.core.hcl import render as render_block
from emissiongate.core.patches._common import append_blocks, tf_name


def schedule_block(name: str, provider: str, suffix: str, cron: str, tz: str, size: int) -> Block:
    return Block(
        "resource",
        ("aws_autoscaling_schedule", f"{name}_{suffix}"),
        (
            Attr("provider", provider),
            Attr("scheduled_action_name", q(f"emissiongate-{suffix}")),
            Attr("autoscaling_group_name", f"aws_autoscaling_group.{name}.name"),
            Attr("recurrence", q(cron)),
            Attr("time_zone", q(tz)),
            Attr("min_size", str(size)),
            Attr("max_size", str(size)),
            Attr("desired_capacity", str(size)),
        ),
    )


def render_blocks(name: str, provider: str, params: dict[str, str]) -> list[str]:
    size = int(params["min_on"])
    tz = params["time_zone"]
    return [
        render_block(schedule_block(name, provider, "off", params["off_cron"], tz, 0)),
        render_block(schedule_block(name, provider, "on", params["on_cron"], tz, size)),
    ]


def render(resource: Resource, text: str, params: dict[str, str], inject_bad: bool) -> str:
    name = tf_name(resource)
    provider = get_attribute(text, "resource", ("aws_autoscaling_group", name), "provider")
    if provider is None:
        raise ValueError(f"{name}: ASG has no provider attribute")
    return append_blocks(text, render_blocks(name, provider, params))
