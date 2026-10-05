"""Energy per resource, METHODOLOGY §1–§2. Every coefficient comes from `core/factors.py`.

cpu_watts  = vcpu × (min_w_cpu + u_cpu × (max_w_cpu − min_w_cpu))
gpu_watts  = gpu_count × (min_w_gpu + u_gpu × (max_w_gpu − min_w_gpu))
mem_watts  = max(0, memory_gib − 4 × vcpu) × memory_kwh_per_gb_hour × 1000   (EG-simplification-1)
wall_watts = (cpu + gpu + mem) × pue
kwh        = wall_watts × hours / 1000
"""

from __future__ import annotations

from dataclasses import dataclass

from emissiongate.contracts import EmissionRecord, EnergyBreakdown, Provenance
from emissiongate.core.factors import FactorNotFound, Factors, Sourced

__all__ = [
    "ComputeEnergy",
    "FactorNotFound",
    "StorageEnergy",
    "compute",
    "emission_record",
    "kg_co2e",
    "storage",
    "storage_medium",
    "weekly_to_annual_hours",
]

HOURS_PER_YEAR = 8760.0
HOURS_PER_WEEK = 168.0
MEMORY_GIB_PER_VCPU_INCLUDED = 4.0  # EG-simplification-1, METHODOLOGY §7
WATTS_PER_KW = 1000.0
G_PER_KG = 1000.0

# Storage class -> (medium, replication key). Classification follows CCF's SSD/HDD usage-type lists
# (METHODOLOGY §3: S3 Standard and archive classes all use the HDD coefficient).
_STORAGE_CLASSES: dict[str, tuple[str, str]] = {
    "gp2": ("ssd", "EC2_EBS_VOLUME"),
    "gp3": ("ssd", "EC2_EBS_VOLUME"),
    "io1": ("ssd", "EC2_EBS_VOLUME"),
    "io2": ("ssd", "EC2_EBS_VOLUME"),
    "st1": ("hdd", "EC2_EBS_VOLUME"),
    "sc1": ("hdd", "EC2_EBS_VOLUME"),
    "STANDARD": ("hdd", "S3"),
    "STANDARD_IA": ("hdd", "S3"),
    "INTELLIGENT_TIERING": ("hdd", "S3"),
    "GLACIER_IR": ("hdd", "S3"),
    "GLACIER": ("hdd", "S3"),
    "DEEP_ARCHIVE": ("hdd", "S3"),
    "ONEZONE_IA": ("hdd", "S3_ONE_ZONE_REDUCED_REDUNDANCY"),
}


@dataclass(frozen=True)
class ComputeEnergy:
    instance_type: str
    u_cpu: float
    u_gpu: float
    hours: float
    count: int
    cpu_watts: float  # per instance
    gpu_watts: float
    memory_watts: float
    it_watts: float
    wall_watts: float
    pue: float
    kwh: float  # all instances, over `hours`
    provenance: tuple[Provenance, ...]

    def breakdown(self) -> EnergyBreakdown:
        return EnergyBreakdown(
            cpu_watts=self.cpu_watts * self.count,
            gpu_watts=self.gpu_watts * self.count,
            memory_watts=self.memory_watts * self.count,
        )


@dataclass(frozen=True)
class StorageEnergy:
    tb: float
    storage_class: str
    medium: str
    replication: int
    coef_wh_per_tb_hour: float
    pue: float
    hours: float
    kwh: float
    provenance: tuple[Provenance, ...]


def _check_unit_interval(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be within 0..1, got {value}")


def weekly_to_annual_hours(hours_per_week: float) -> float:
    return hours_per_week * HOURS_PER_YEAR / HOURS_PER_WEEK


def compute(
    factors: Factors,
    instance_type: str,
    u_cpu: float,
    u_gpu: float | None = None,
    hours: float = HOURS_PER_YEAR,
    count: int = 1,
) -> ComputeEnergy:
    if hours < 0 or count < 0:
        raise ValueError("hours and count must be non-negative")
    spec_s = factors.instance(instance_type)
    spec = spec_s.value
    if u_gpu is None:
        if spec.gpu_count > 0:
            raise ValueError(f"{instance_type} has a GPU: u_gpu is required, never defaulted")
        u_gpu = 0.0
    _check_unit_interval("u_cpu", u_cpu)
    _check_unit_interval("u_gpu", u_gpu)
    mem_coef = factors.constant("memory_kwh_per_gb_hour")
    pue = factors.pue()

    cpu_watts = spec.vcpu * (
        spec.min_watts_per_vcpu + u_cpu * (spec.max_watts_per_vcpu - spec.min_watts_per_vcpu)
    )
    gpu_watts = spec.gpu_count * (
        spec.gpu_min_watts + u_gpu * (spec.gpu_max_watts - spec.gpu_min_watts)
    )
    excess_gib = max(0.0, spec.memory_gib - MEMORY_GIB_PER_VCPU_INCLUDED * spec.vcpu)
    memory_watts = excess_gib * mem_coef.value * WATTS_PER_KW
    it_watts = cpu_watts + gpu_watts + memory_watts
    wall_watts = it_watts * pue.value
    kwh = wall_watts * hours * count / WATTS_PER_KW
    return ComputeEnergy(
        instance_type=instance_type,
        u_cpu=u_cpu,
        u_gpu=u_gpu,
        hours=hours,
        count=count,
        cpu_watts=cpu_watts,
        gpu_watts=gpu_watts,
        memory_watts=memory_watts,
        it_watts=it_watts,
        wall_watts=wall_watts,
        pue=pue.value,
        kwh=kwh,
        provenance=(spec_s.provenance,),
    )


def storage_medium(storage_class: str) -> tuple[str, str]:
    try:
        return _STORAGE_CLASSES[storage_class]
    except KeyError as exc:
        raise FactorNotFound(f"storage class {storage_class!r} has no medium mapping") from exc


def storage(
    factors: Factors, tb: float, storage_class: str, hours: float = HOURS_PER_YEAR
) -> StorageEnergy:
    if tb < 0 or hours < 0:
        raise ValueError("tb and hours must be non-negative")
    medium, replication_key = storage_medium(storage_class)
    coef = factors.constant("ssd_wh_per_tb_hour" if medium == "ssd" else "hdd_wh_per_tb_hour")
    replication = factors.replication(replication_key)
    pue = factors.pue()
    kwh = tb * coef.value * replication.value * pue.value * hours / WATTS_PER_KW
    return StorageEnergy(
        tb=tb,
        storage_class=storage_class,
        medium=medium,
        replication=replication.value,
        coef_wh_per_tb_hour=coef.value,
        pue=pue.value,
        hours=hours,
        kwh=kwh,
        provenance=(coef.provenance,),
    )


def kg_co2e(kwh: float, g_per_kwh: float) -> float:
    return kwh * g_per_kwh / G_PER_KG


def emission_record(
    resource_id: str,
    kwh_yr: float,
    intensity: Sourced[float],
    pue: float,
    breakdown: EnergyBreakdown,
    provenance: tuple[Provenance, ...] | list[Provenance],
    ledger_event_id: int,
) -> EmissionRecord:
    """Build an EmissionRecord carrying coefficient provenance plus the grid tier used."""
    merged: list[Provenance] = []
    for p in [*provenance, intensity.provenance]:
        if p not in merged:
            merged.append(p)
    return EmissionRecord(
        resource_id=resource_id,
        kwh_yr=kwh_yr,
        kg_co2e_yr=kg_co2e(kwh_yr, intensity.value),
        g_per_kwh=intensity.value,
        pue=pue,
        breakdown=breakdown,
        provenance=merged,
        ledger_event_id=ledger_event_id,
    )
