"""Guardrails from policy.yaml and suppressions.yaml (AGENTS.md invariant 6). Fail closed.

Order: suppressions, protected tags (refuse), missing required tags (protect), restrictions
(allow-list), advisory-only kinds. Unknown or malformed policy input raises `PolicyError`; it never
means "allowed".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from emissiongate.contracts import Intervention, Resource

ALL_INTERVENTIONS: tuple[Intervention, ...] = (
    "rightsize",
    "schedule",
    "graviton",
    "storage_tier",
    "time_shift",
)
REQUIRED_KEYS = (
    "required_tags",
    "missing_required_tag",
    "protected_tags",
    "schedule_allowed_environments",
    "advisory_only",
    "thresholds",
    "ceilings",
)


class PolicyError(ValueError):
    """policy.yaml or suppressions.yaml is missing a key or has an unknown value."""


@dataclass(frozen=True)
class Verdict:
    resource_id: str
    allowed: tuple[Intervention, ...]
    blocked_by: tuple[str, ...] = ()
    forbid: tuple[str, ...] = ()
    suppressed_by: tuple[str, ...] = ()

    @property
    def refused(self) -> bool:
        return not self.allowed


@dataclass(frozen=True)
class Policy:
    raw: dict
    suppressions: tuple[dict, ...] = field(default_factory=tuple)

    @classmethod
    def from_docs(cls, policy: dict, suppressions: dict | None) -> Policy:
        if not isinstance(policy, dict):
            raise PolicyError("policy must be a mapping")
        missing = [k for k in REQUIRED_KEYS if k not in policy]
        if missing:
            raise PolicyError(f"policy.yaml missing keys: {missing}")
        if policy["missing_required_tag"] != "protect":
            raise PolicyError("missing_required_tag must be 'protect' (fail closed)")
        for rule in policy["protected_tags"]:
            if rule.get("action") not in ("refuse", "restrict"):
                raise PolicyError(f"unknown protected_tags action: {rule.get('action')!r}")
        if suppressions is None or "suppressions" not in suppressions:
            raise PolicyError("suppressions.yaml must contain a 'suppressions' list")
        entries = suppressions["suppressions"] or []
        for e in entries:
            if "resource_id" not in e or "intervention" not in e:
                raise PolicyError(f"malformed suppression entry: {e}")
        return cls(policy, tuple(entries))

    @property
    def thresholds(self) -> dict:
        return self.raw["thresholds"]

    @property
    def ceilings(self) -> dict:
        return self.raw["ceilings"]

    @property
    def gate(self) -> dict:
        if "gate" not in self.raw:
            raise PolicyError("policy.yaml has no 'gate' section")
        return self.raw["gate"]

    @property
    def advisory_only(self) -> tuple[str, ...]:
        return tuple(self.raw["advisory_only"])

    def schedule_allowed(self, tags: dict[str, str]) -> bool:
        if tags.get("ScheduleOk", "").lower() == "true":
            return True
        return tags.get("Environment") in self.raw["schedule_allowed_environments"]

    def _suppressed(self, resource_id: str, today: date) -> list[tuple[str, str]]:
        out = []
        for e in self.suppressions:
            if e["resource_id"] != resource_id:
                continue
            until = e.get("until")
            if until and date.fromisoformat(str(until)) < today:
                continue
            out.append((str(e["intervention"]), str(e.get("label", "suppressed"))))
        return out

    def evaluate(self, resource: Resource, today: date) -> Verdict:
        tags = resource.tags
        refusals: list[str] = []
        restrictions: list[str] = []
        forbid: list[str] = []
        allowed: list[Intervention] = list(ALL_INTERVENTIONS)

        for rule in self.raw["protected_tags"]:
            value = tags.get(rule["key"])
            if value is None or value not in rule["values"]:
                continue
            label = f"tag:{rule['key']}={value}"
            if rule["action"] == "refuse":
                refusals.append(label)
            else:  # restrict
                allow = rule.get("allow_interventions")
                if not isinstance(allow, list):
                    raise PolicyError(f"restrict rule for {label} needs allow_interventions")
                allowed = [i for i in allowed if i in allow]
                forbid.extend(rule.get("forbid", []))
                restrictions.append(f"{label} (restricted to {', '.join(allow)})")

        for key in self.raw["required_tags"]:
            if not tags.get(key):
                refusals.append(f"missing-tag:{key}")

        if refusals:
            allowed = []
        blocked = refusals + restrictions

        suppressed = self._suppressed(resource.resource_id, today)
        suppressed_by = []
        for intervention, label in suppressed:
            allowed = [] if intervention == "*" else [i for i in allowed if i != intervention]
            suppressed_by.append(f"{label}:{intervention}")

        return Verdict(
            resource_id=resource.resource_id,
            allowed=tuple(allowed),
            blocked_by=tuple(blocked),
            forbid=tuple(forbid),
            suppressed_by=tuple(suppressed_by),
        )
