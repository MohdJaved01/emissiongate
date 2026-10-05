"""Golden values G5–G7, METHODOLOGY §6 (PR gate projections). 3 decimal places."""

import pytest

from emissiongate.core import projection as pj
from emissiongate.core.factors import Factors
from emissiongate.estate.generator import PRICES_USD_PER_HOUR_SYNTHETIC as PRICES

GATE = {"assumed_utilisation_band": [0.10, 0.90], "assumed_gpu_utilisation": 0.50}


def g(value: float) -> object:
    return pytest.approx(value, abs=5e-4)


@pytest.fixture(scope="module")
def factors() -> Factors:
    return Factors.load()


def test_g5_new_gpu_fleet_is_assumed_with_band(factors: Factors) -> None:
    after = pj.UnitState("g5.2xlarge", 2, "us-east-1", 8760.0)
    p = pj.project("aws_autoscaling_group.gpu_fleet", None, after, None, factors, GATE, PRICES)
    assert p.basis == "assumed"
    assert p.kg_co2e_yr_before == 0.0
    assert p.kg_co2e_yr_after == g(683.517)
    assert p.kg_co2e_yr_after_low == g(263.097)
    assert p.kg_co2e_yr_after_high == g(1103.937)
    assert p.kwh_yr_delta == g(1871.993)


def test_g6_scale_out_holds_work_constant(factors: Factors) -> None:
    before = pj.UnitState("m5.2xlarge", 6, "eu-west-1", 8760.0)
    after = pj.UnitState("m5.2xlarge", 10, "eu-west-1", 8760.0)
    obs = pj.Observed(u_cpu=0.60, u_gpu=None, p95_cpu=0.64)
    p = pj.project("aws_autoscaling_group.legacy_worker", before, after, obs, factors, GATE, PRICES)
    assert p.basis == "observed_projected"
    assert p.kg_co2e_yr_before == g(393.593)
    assert p.kg_co2e_yr_after == g(452.788)
    assert round(p.kg_co2e_yr_after, 3) - round(p.kg_co2e_yr_before, 3) == g(59.195)
    sugg = pj.UnitState("m7g.2xlarge", 10, "eu-west-1", 8760.0)
    head_u = pj.projected_u(before, after, obs)
    s = pj.energy_kg(factors, sugg, head_u)
    assert s.kwh == g(723.185)
    assert s.kg == g(220.571)
    assert round(s.kg, 3) - round(p.kg_co2e_yr_after, 3) == g(-232.217)


def test_g7_region_move_observed(factors: Factors) -> None:
    before = pj.UnitState("c5.2xlarge", 4, "eu-west-2", 730.0)
    after = pj.UnitState("c5.2xlarge", 4, "eu-north-1", 730.0)
    obs = pj.Observed(u_cpu=0.80, u_gpu=None, p95_cpu=0.85)
    p = pj.project("aws_autoscaling_group.nightly_etl", before, after, obs, factors, GATE, PRICES)
    assert p.basis == "observed"
    assert p.kg_co2e_yr_before == g(27.446)
    assert p.kg_co2e_yr_after == g(0.720)
    assert round(p.kg_co2e_yr_after, 3) - round(p.kg_co2e_yr_before, 3) == g(-26.726)


def test_schedule_hours(factors: Factors) -> None:
    assert pj.hours_per_year([]) == 8760.0
    daily = [("0 2 * * *", "Europe/London", 4), ("0 4 * * *", "Europe/London", 0)]
    assert pj.hours_per_year(daily) == g(730.0)
    weekdays = [("0 8 * * MON-FRI", "America/New_York", 4), ("0 20 * * MON-FRI", "x", 0)]
    assert pj.hours_per_year(weekdays) == g(60 * 8760 / 168)


def test_numeric_cron_days_and_bad_recurrences(factors: Factors) -> None:
    numeric = [("0 8 * * 1-5", "x", 4), ("0 20 * * 1-5", "x", 0)]
    assert pj.hours_per_year(numeric) == g(60 * 8760 / 168)
    with pytest.raises(ValueError):
        pj.hours_per_year([("@daily", "x", 4), ("0 20 * * *", "x", 0)])


def test_removed_assumed_resource_has_a_band(factors: Factors) -> None:
    before = pj.UnitState("g5.2xlarge", 2, "us-east-1", 8760.0)
    p = pj.project("aws_autoscaling_group.gpu_fleet", before, None, None, factors, GATE, PRICES)
    assert p.basis == "assumed"
    assert p.kg_co2e_yr_before_low == g(263.097)
    assert p.kg_co2e_yr_before_high == g(1103.937)


def test_removed_resource_is_negative(factors: Factors) -> None:
    before = pj.UnitState("m5.2xlarge", 6, "eu-west-1", 8760.0)
    obs = pj.Observed(u_cpu=0.60, u_gpu=None, p95_cpu=0.64)
    p = pj.project("aws_autoscaling_group.legacy_worker", before, None, obs, factors, GATE, PRICES)
    assert p.kg_co2e_yr_after == 0.0
    assert p.kg_co2e_yr_before == g(393.593)


def test_unknown_type_is_not_quantified(factors: Factors) -> None:
    after = pj.UnitState("x9.mega", 1, "us-east-1", 8760.0)
    p = pj.project("aws_instance.mystery", None, after, None, factors, GATE, PRICES)
    assert p.quantified is False
    assert "x9.mega" in (p.reason or "")


def test_missing_price_is_never_a_silent_zero(factors: Factors) -> None:
    after = pj.UnitState("g5.2xlarge", 2, "us-east-1", 8760.0)
    p = pj.project("aws_autoscaling_group.gpu_fleet", None, after, None, factors, GATE, None)
    assert p.quantified is False and "price" in (p.reason or "")
