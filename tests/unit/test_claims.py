import pytest

from emissiongate.core.claims import has_numeric_claim


@pytest.mark.parametrize(
    "text",
    [
        "This saves 258 kg a year.",
        "Cuts emissions by 64%.",
        "Saves $27,000.",
        "about 0.7 t CO2e",
        "reduces 700 kWh annually",
        "USD 300 saved",
        "a 40 percent drop",
    ],
)
def test_numeric_claims_are_caught(text: str) -> None:
    assert has_numeric_claim(text)


@pytest.mark.parametrize(
    "text",
    [
        "Scaling to zero outside business hours removes idle energy.",
        "Moves the batch to a lower-carbon window; kgCO2e figures come from the core.",
        "The g5.2xlarge fleet runs around the clock.",
        "Requires an arm64 build of version 2 of the image.",
    ],
)
def test_prose_without_claims_passes(text: str) -> None:
    assert not has_numeric_claim(text)
