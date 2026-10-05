"""Patch templates (INTERVENTIONS.md, ADR-0005). The model never writes HCL.

A renderer takes a validated decision and the candidate's own file, and returns the complete new
contents of that file only. No renderer can emit `expiration`, deletion or resource removal.
"""

from __future__ import annotations

from collections.abc import Callable

from emissiongate.contracts import Candidate, Intervention, PatchDecision, Resource
from emissiongate.core.patches import graviton, rightsize, schedule, storage_tier, time_shift

Renderer = Callable[[Resource, str, dict[str, str], bool], str]

REGISTRY: dict[Intervention, Renderer] = {
    "rightsize": rightsize.render,
    "schedule": schedule.render,
    "graviton": graviton.render,
    "storage_tier": storage_tier.render,
    "time_shift": time_shift.render,
}
FORBIDDEN_TOKENS = ("expiration", "force_destroy", "prevent_destroy")


class PatchError(ValueError):
    pass


def validate_params(candidate: Candidate, decision: PatchDecision) -> list[str]:
    """Keys must be option names; values must be in the allowed lists (DATA_CONTRACTS rules)."""
    errors: list[str] = []
    if decision.candidate_id != candidate.candidate_id:
        errors.append("candidate_id does not match")
    if decision.template != candidate.intervention:
        errors.append(f"template {decision.template!r} is not {candidate.intervention!r}")
    options = {o.name: o.allowed for o in candidate.options}
    for name, value in decision.params.items():
        if name not in options:
            errors.append(f"unknown parameter {name!r}")
        elif value not in options[name]:
            errors.append(f"{name}={value!r} not in allowed values {options[name]}")
    for name in options:
        if name not in decision.params:
            errors.append(f"missing parameter {name!r}")
    return errors


def render(
    template: Intervention,
    resource: Resource,
    file_text: str,
    params: dict[str, str],
    forbid: tuple[str, ...] = (),
    inject_bad_param: bool = False,
) -> dict[str, str]:
    """Return {tf_file: complete new contents} for the candidate's own file."""
    if resource.tf_file is None:
        raise PatchError(f"{resource.resource_id} has no Terraform file")
    try:
        renderer = REGISTRY[template]
    except KeyError as exc:
        raise PatchError(f"unknown template {template!r}") from exc
    new_text = renderer(resource, file_text, params, inject_bad_param)
    for token in FORBIDDEN_TOKENS:
        if token in new_text and token not in file_text:
            raise PatchError(f"renderer produced forbidden token {token!r}")
    if "expiration" in forbid and "expiration" in new_text:
        raise PatchError("expiration is forbidden for this resource")
    if new_text == file_text:
        raise PatchError("renderer produced no change")
    return {resource.tf_file: new_text}
