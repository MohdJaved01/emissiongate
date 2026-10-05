"""storage_tier: a lifecycle configuration with a transition only. Never an expiration block."""

from __future__ import annotations

from emissiongate.contracts import Resource
from emissiongate.core.hcl import Attr, Block, get_attribute, q
from emissiongate.core.hcl import render as render_block
from emissiongate.core.patches._common import append_blocks, tf_name


def render(resource: Resource, text: str, params: dict[str, str], inject_bad: bool) -> str:
    name = tf_name(resource)
    provider = get_attribute(text, "resource", ("aws_s3_bucket", name), "provider")
    if provider is None:
        raise ValueError(f"{name}: bucket has no provider attribute")
    block = Block(
        "resource",
        ("aws_s3_bucket_lifecycle_configuration", name),
        (
            Attr("provider", provider),
            Attr("bucket", f"aws_s3_bucket.{name}.id"),
            None,
            Block(
                "rule",
                body=(
                    Attr("id", q("emissiongate-tier")),
                    Attr("status", q("Enabled")),
                    None,
                    Block("filter"),
                    None,
                    Block(
                        "transition",
                        body=(
                            Attr("days", str(int(params["transition_days"]))),
                            Attr("storage_class", q(params["storage_class"])),
                        ),
                    ),
                ),
            ),
        ),
    )
    return append_blocks(text, [render_block(block)])
