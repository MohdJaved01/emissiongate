"""core.verdict: net delta and check status from projections (GATE §3). Hand-checkable numbers."""

from __future__ import annotations

import math

import pytest

from emissiongate.contracts import Projection
from emissiongate.core.verdict import conclusion, totals, verdict

GATE = {"warn_kg_co2e_yr": 25.0, "ack_kg_co2e_yr": 100.0}


def _p(before: float, after: float, *, low=None, high=None, quantified=True) -> Projection:
    return Projection(
        address=f"aws_autoscaling_group.x{before}{after}",
        basis="assumed" if low is not None else "observed",
        kg_co2e_yr_before=before,
        kg_co2e_yr_after=after,
        kg_co2e_yr_after_low=low,
        kg_co2e_yr_after_high=high,
        kwh_yr_delta=0.0,
        usd_synthetic_yr_delta=0.0,
        provenance=[],
        quantified=quantified,
    )


def test_totals_sum_quantified_rows_only() -> None:
    t = totals([_p(10, 40), _p(50, 20), _p(0, 999, quantified=False)])
    assert t.net == pytest.approx(0.0)  # +30 - 30; the unquantified row is ignored
    assert (t.low, t.high) == (pytest.approx(0.0), pytest.approx(0.0))


def test_assumed_rows_carry_their_band() -> None:
    t = totals([_p(0, 60, low=20, high=100), _p(10, 15)])
    assert t.net == pytest.approx(65.0)
    assert t.low == pytest.approx(25.0)  # 20 + 5
    assert t.high == pytest.approx(105.0)  # 100 + 5


@pytest.mark.parametrize(
    ("after", "status"),
    [
        (124.9, "pass"),
        (125.0, "pass_with_warning"),
        (199.9, "pass_with_warning"),
        (200.0, "ack_required"),
    ],
)
def test_thresholds_are_inclusive(after: float, status: str) -> None:
    got, reason, t = verdict("pass", [_p(100, after)], GATE)
    assert got == status and reason is None
    assert t.net == pytest.approx(after - 100)


def test_nothing_quantifiable_is_not_evaluated() -> None:
    got, reason, _ = verdict("pass", [_p(0, 500, quantified=False)], GATE)
    assert (got, reason) == ("not_evaluated", "nothing quantifiable")


def test_no_projections_passes() -> None:
    assert verdict("pass", [], GATE)[0] == "pass"


def test_not_evaluated_stays_not_evaluated() -> None:
    assert verdict("not_evaluated", [_p(0, 500)], GATE)[0] == "not_evaluated"


@pytest.mark.parametrize("prior", ["accepted", "ack_required", "pass_with_warning", "bogus"])
def test_only_pass_or_not_evaluated_are_inputs(prior: str) -> None:
    """Acceptance is decided by the publisher, never carried in from an evaluation."""
    with pytest.raises(ValueError):
        verdict(prior, [_p(0, 1)], GATE)


def test_missing_threshold_fails_loudly() -> None:
    with pytest.raises(KeyError):
        verdict("pass", [_p(0, 500)], {"warn_kg_co2e_yr": 25.0})


def test_non_finite_totals_fail_loudly() -> None:
    """NaN compares false with every threshold; it must never read as a pass."""
    with pytest.raises(ValueError):
        verdict("pass", [_p(0, math.nan)], GATE)
    with pytest.raises(ValueError):
        verdict("pass", [_p(0, math.inf)], GATE)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("pass", "success"),
        ("pass_with_warning", "success"),
        ("accepted", "success"),
        ("ack_required", "failure"),
    ],
)
def test_conclusions(status: str, expected: str) -> None:
    assert conclusion(status, GATE) == expected


def test_not_evaluated_follows_policy_and_fails_closed_when_unset() -> None:
    assert conclusion("not_evaluated", {**GATE, "not_evaluated_conclusion": "neutral"}) == "neutral"
    assert conclusion("not_evaluated", {**GATE, "not_evaluated_conclusion": "failure"}) == "failure"
    assert conclusion("not_evaluated", GATE) == "failure"
    with pytest.raises(ValueError):
        conclusion("not_evaluated", {**GATE, "not_evaluated_conclusion": "success"})
