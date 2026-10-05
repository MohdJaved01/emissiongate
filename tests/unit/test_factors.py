import pytest

from emissiongate.core.factors import FactorNotFound, Factors

ESTATE_TYPES = [
    "g5.2xlarge",
    "m5.large",
    "m5.2xlarge",
    "db.r5.4xlarge",
    "c5.2xlarge",
    "m7g.xlarge",
    "c5.4xlarge",
]


@pytest.fixture(scope="module")
def factors() -> Factors:
    return Factors.load()


@pytest.mark.parametrize("instance_type", ESTATE_TYPES)
def test_every_estate_instance_type_resolves(factors: Factors, instance_type: str) -> None:
    sourced = factors.instance(instance_type)
    assert sourced.value.vcpu > 0
    assert sourced.provenance.source == "ccf@f584c54"
    assert sourced.provenance.version.startswith("f584c549")
    assert sourced.provenance.tier == "vendored"


def test_g5_2xlarge_shape(factors: Factors) -> None:
    spec = factors.instance("g5.2xlarge").value
    assert (spec.vcpu, spec.memory_gib, spec.gpu, spec.gpu_count) == (8, 32, "Nvidia A10G", 1)
    assert (spec.min_watts_per_vcpu, spec.max_watts_per_vcpu) == (0.47, 1.69)
    assert (spec.gpu_min_watts, spec.gpu_max_watts) == (18.0, 153.0)
    assert spec.arch == "x86_64"


def test_multi_processor_instance_averages_watts(factors: Factors) -> None:
    spec = factors.instance("db.r5.4xlarge").value
    assert len(spec.processors) == 2
    assert spec.min_watts_per_vcpu == pytest.approx(0.65)
    assert spec.max_watts_per_vcpu == pytest.approx(4.08)


def test_graviton_is_arm(factors: Factors) -> None:
    assert factors.instance("m7g.2xlarge").value.arch == "arm64"
    assert factors.instance("m5.2xlarge").value.arch == "x86_64"


def test_unknown_instance_type_raises(factors: Factors) -> None:
    with pytest.raises(FactorNotFound):
        factors.instance("x9z.mega")


@pytest.mark.parametrize("region", ["mars-north-1", "unknown"])
def test_unknown_region_raises(factors: Factors, region: str) -> None:
    with pytest.raises(FactorNotFound):
        factors.region_g_per_kwh(region)


def test_region_is_annual_tier(factors: Factors) -> None:
    sourced = factors.region_g_per_kwh("us-east-1")
    assert sourced.value == pytest.approx(365.1278)
    assert sourced.provenance.tier == "annual"
    assert factors.region_g_per_kwh("eu-north-1").value == 8.0


def test_constants(factors: Factors) -> None:
    assert factors.pue().value == 1.135
    assert factors.replication("S3").value == 6
    assert factors.replication("EC2_EBS_VOLUME").value == 2
    with pytest.raises(FactorNotFound):
        factors.constant("made_up")
