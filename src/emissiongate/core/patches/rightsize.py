"""rightsize: change instance_type (launch template) or instance_class (RDS)."""

from __future__ import annotations

from emissiongate.contracts import Resource
from emissiongate.core.hcl import q, set_attribute
from emissiongate.core.patches._common import tf_name


def render(resource: Resource, text: str, params: dict[str, str], inject_bad: bool) -> str:
    target = params["target_instance_type"]
    name = tf_name(resource)
    if resource.kind == "rds":
        return set_attribute(
            text, "resource", ("aws_db_instance", name), "instance_class", q(target)
        )
    return set_attribute(
        text, "resource", ("aws_launch_template", name), "instance_type", q(target)
    )
