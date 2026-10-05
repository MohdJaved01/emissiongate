"""graviton: arm64 instance type and image variable in the launch template (two lines)."""

from __future__ import annotations

from emissiongate.contracts import Resource
from emissiongate.core.hcl import q, set_attribute
from emissiongate.core.patches._common import tf_name

# `run --inject bad-param`: the first render references an image variable that does not exist,
# so validation fails and the repair loop must recover (SYNTHETIC_ESTATE §6).
BAD_IMAGE_PARAM = "ami_arm64_latest"


def render(resource: Resource, text: str, params: dict[str, str], inject_bad: bool) -> str:
    labels = ("aws_launch_template", tf_name(resource))
    image = BAD_IMAGE_PARAM if inject_bad else params["image_param"]
    text = set_attribute(
        text, "resource", labels, "instance_type", q(params["target_instance_type"])
    )
    return set_attribute(text, "resource", labels, "image_id", f"var.{image}")
