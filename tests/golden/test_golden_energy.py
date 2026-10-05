"""Golden values G1–G4, METHODOLOGY §6. They must match to 3 decimal places."""

import pytest

from emissiongate.core import energy
from emissiongate.core.factors import Factors
from emissiongate.core.grid import annual_intensity

HOURS_YR = 8760.0


def g(value: float) -> object:
    """Match to 3 decimal places."""
    return pytest.approx(value, abs=5e-4)


def saving(before: float, after: float) -> float:
    """METHODOLOGY §6 savings are differences of the published (rounded) before/after values."""
    return round(before, 3) - round(after, 3)


@pytest.fixture(scope="module")
def factors() -> Factors:
    return Factors.load()


def test_g1_idle_gpu_instance(factors: Factors) -> None:
    e = energy.compute(factors, "g5.2xlarge", u_cpu=0.05, u_gpu=0.04, hours=HOURS_YR)
    assert e.it_watts == g(27.648)
    assert e.wall_watts == g(31.3805)
    assert e.kwh == g(274.893)
    i = annual_intensity(factors, "us-east-1").value
    assert energy.kg_co2e(e.kwh, i) == g(100.371)
    sched = energy.compute(
        factors, "g5.2xlarge", u_cpu=0.05, u_gpu=0.04, hours=energy.weekly_to_annual_hours(60)
    )
    assert sched.kwh == g(98.176)
    assert energy.kg_co2e(sched.kwh, i) == g(35.847)
    assert saving(energy.kg_co2e(e.kwh, i), energy.kg_co2e(sched.kwh, i)) == g(64.524)


def test_g2_graviton(factors: Factors) -> None:
    i = annual_intensity(factors, "eu-west-1").value
    x86 = energy.compute(factors, "m5.2xlarge", u_cpu=0.60, hours=HOURS_YR)
    assert (x86.it_watts, x86.wall_watts, x86.kwh) == (g(21.632), g(24.5523), g(215.078))
    assert energy.kg_co2e(x86.kwh, i) == g(65.599)
    arm = energy.compute(factors, "m7g.2xlarge", u_cpu=0.60, hours=HOURS_YR)
    assert (arm.it_watts, arm.wall_watts, arm.kwh) == (g(9.616), g(10.9142), g(95.608))
    assert energy.kg_co2e(arm.kwh, i) == g(29.160)
    assert saving(energy.kg_co2e(x86.kwh, i), energy.kg_co2e(arm.kwh, i)) == g(36.439)
    assert energy.kg_co2e(x86.kwh - arm.kwh, i) == g(36.4384)  # unrounded


def test_g3_database_rightsize(factors: Factors) -> None:
    i = annual_intensity(factors, "us-east-1").value
    big = energy.compute(factors, "db.r5.4xlarge", u_cpu=0.05, hours=HOURS_YR)
    assert big.it_watts == g(38.232)
    assert big.memory_watts == g(25.088)
    assert (big.wall_watts, big.kwh) == (g(43.3933), g(380.125))
    assert energy.kg_co2e(big.kwh, i) == g(138.794)
    small = energy.compute(factors, "db.r5.xlarge", u_cpu=0.20, hours=HOURS_YR)
    assert (small.it_watts, small.wall_watts, small.kwh) == (g(11.616), g(13.1842), g(115.493))
    assert energy.kg_co2e(small.kwh, i) == g(42.170)
    assert saving(energy.kg_co2e(big.kwh, i), energy.kg_co2e(small.kwh, i)) == g(96.624)
    assert energy.kg_co2e(big.kwh - small.kwh, i) == g(96.6246)  # unrounded


def test_g4_storage(factors: Factors) -> None:
    ebs = energy.storage(factors, tb=8 * 0.5, storage_class="gp3", hours=HOURS_YR)
    assert ebs.kwh == g(95.449)
    assert energy.kg_co2e(ebs.kwh, annual_intensity(factors, "us-east-1").value) == g(34.851)
    s3 = energy.storage(factors, tb=40, storage_class="STANDARD", hours=HOURS_YR)
    assert s3.kwh == g(1551.046)
    assert energy.kg_co2e(s3.kwh, annual_intensity(factors, "eu-west-2").value) == g(473.069)
    archive = energy.storage(factors, tb=40, storage_class="GLACIER_IR", hours=HOURS_YR)
    assert s3.kwh - archive.kwh == g(0.0)


def test_provenance_on_every_figure(factors: Factors) -> None:
    e = energy.compute(factors, "g5.2xlarge", u_cpu=0.05, u_gpu=0.04, hours=HOURS_YR)
    assert e.provenance and all(p.source == "ccf@f584c54" for p in e.provenance)
    assert annual_intensity(factors, "us-east-1").provenance.tier == "annual"


def test_utilisation_out_of_range_raises(factors: Factors) -> None:
    with pytest.raises(ValueError):
        energy.compute(factors, "m5.large", u_cpu=1.2, hours=1)


def test_unknown_storage_class_raises(factors: Factors) -> None:
    with pytest.raises(energy.FactorNotFound):
        energy.storage(factors, tb=1, storage_class="FLOPPY", hours=1)


def test_emission_record_carries_annual_tier(factors: Factors) -> None:
    e = energy.compute(factors, "g5.2xlarge", u_cpu=0.05, u_gpu=0.04, hours=HOURS_YR, count=4)
    rec = energy.emission_record(
        "gpu-inference",
        e.kwh,
        annual_intensity(factors, "us-east-1"),
        e.pue,
        e.breakdown(),
        e.provenance,
        ledger_event_id=7,
    )
    assert rec.kg_co2e_yr == g(401.484)
    assert {p.tier for p in rec.provenance} == {"vendored", "annual"}
    assert rec.ledger_event_id == 7


def test_gpu_utilisation_is_never_defaulted(factors: Factors) -> None:
    with pytest.raises(ValueError, match="u_gpu is required"):
        energy.compute(factors, "g5.2xlarge", u_cpu=0.05)
