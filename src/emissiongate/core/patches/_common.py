"""Helpers shared by the templates."""

from __future__ import annotations

from emissiongate.contracts import Resource


def tf_name(resource: Resource) -> str:
    if not resource.tf_address:
        raise ValueError(f"{resource.resource_id} has no Terraform address")
    return resource.tf_address.split(".", 1)[1]


def append_blocks(text: str, blocks: list[str]) -> str:
    return text.rstrip("\n") + "\n\n" + "\n\n".join(blocks) + "\n"
