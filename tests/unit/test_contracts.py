import typing

import pytest
from pydantic import ValidationError

from emissiongate import contracts as c


def test_models_are_frozen_and_strict() -> None:
    p = c.Provenance(source="ccf@f584c54", version="f584c549", tier="annual")
    with pytest.raises(ValidationError):
        p.source = "x"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        c.Provenance(source="a", version="b", tier="annual", extra_field=1)  # type: ignore[call-arg]


@pytest.mark.parametrize("model", [c.ScanPlan, c.Classification, c.PatchDecision, c.Narrative])
def test_llm_facing_models_have_no_numeric_fields(model: type) -> None:
    """Invariant 1: the LLM cannot even express a number in a typed field."""
    for name, field in model.model_fields.items():
        args = typing.get_args(field.annotation) or (field.annotation,)
        assert float not in args and int not in args, f"{model.__name__}.{name} is numeric"


def test_resource_is_always_synthetic() -> None:
    r = c.Resource(resource_id="x", kind="ec2", region="us-east-1", tags={})
    assert r.synthetic is True
    with pytest.raises(ValidationError):
        c.Resource(resource_id="x", kind="ec2", region="us-east-1", tags={}, synthetic=False)
