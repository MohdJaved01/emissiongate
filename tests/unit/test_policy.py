from datetime import date

import pytest

from emissiongate.config import load_settings
from emissiongate.contracts import Resource
from emissiongate.core.policy import Policy, PolicyError

SETTINGS = load_settings()
TODAY = date(2026, 10, 5)


def _policy(**over) -> Policy:
    raw = SETTINGS.policy() | over
    return Policy.from_docs(raw, {"suppressions": []})


def _res(tags: dict[str, str]) -> Resource:
    return Resource(resource_id="r", kind="ec2_asg", region="eu-west-1", tags=tags)


def test_missing_required_tag_fails_closed() -> None:
    v = _policy().evaluate(_res({"Environment": "dev"}), TODAY)
    assert v.refused and "missing-tag:Owner" in v.blocked_by


def test_protected_tag_refuses() -> None:
    v = _policy().evaluate(_res({"Environment": "prod", "Owner": "x", "Role": "DR"}), TODAY)
    assert v.refused


def test_regulatory_retention_restricts_to_tiering() -> None:
    tags = {"Environment": "prod", "Owner": "x", "Retention": "Regulatory"}
    v = _policy().evaluate(_res(tags), TODAY)
    assert v.allowed == ("storage_tier",)
    assert "expiration" in v.forbid


def test_unknown_policy_state_raises() -> None:
    with pytest.raises(PolicyError):
        Policy.from_docs({"required_tags": []}, {"suppressions": []})
    with pytest.raises(PolicyError):
        Policy.from_docs(SETTINGS.policy(), None)
    with pytest.raises(PolicyError):
        _policy(missing_required_tag="allow")


def test_suppression_removes_intervention_until_expiry() -> None:
    sup = {
        "suppressions": [{"resource_id": "r", "intervention": "schedule", "until": "2026-12-01"}]
    }
    p = Policy.from_docs(SETTINGS.policy(), sup)
    v = p.evaluate(_res({"Environment": "dev", "Owner": "x"}), TODAY)
    assert "schedule" not in v.allowed
    v_later = p.evaluate(_res({"Environment": "dev", "Owner": "x"}), date(2027, 1, 1))
    assert "schedule" in v_later.allowed
