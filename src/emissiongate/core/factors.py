"""Vendored Cloud Carbon Footprint coefficients, each returned with its provenance.

Every coefficient used anywhere in EmissionGate comes through this module (AGENTS.md invariant 5).
Unknown instance types, processors or regions raise `FactorNotFound`; nothing is defaulted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from emissiongate.contracts import Provenance

FACTORS_FILE = "ccf_aws_f584c54.json"
GRAVITON_PREFIX = "AWS Graviton"


class FactorNotFound(LookupError):
    """A coefficient the methodology needs is not in the vendored factors file."""


@dataclass(frozen=True)
class Sourced[T]:
    value: T
    provenance: Provenance


@dataclass(frozen=True)
class InstanceSpec:
    instance_type: str
    vcpu: int
    memory_gib: float
    processors: tuple[str, ...]
    min_watts_per_vcpu: float  # averaged over processors, as CCF does
    max_watts_per_vcpu: float
    gpu: str | None
    gpu_count: int
    gpu_min_watts: float
    gpu_max_watts: float
    arch: Literal["x86_64", "arm64"]

    @property
    def family(self) -> str:
        return self.instance_type.rsplit(".", 1)[0]

    @property
    def size(self) -> str:
        return self.instance_type.rsplit(".", 1)[1]


def default_factors_dir() -> Path:
    """`factors/` at the repository root (editable install). config.py may pass another path."""
    return Path(__file__).resolve().parents[3] / "factors"


class Factors:
    """Read-only view of one vendored factors file."""

    def __init__(self, data: dict, file_name: str = FACTORS_FILE) -> None:
        self._data = data
        meta = data["_provenance"]
        self.commit: str = meta["commit"]
        self.file_name = file_name
        self.short_sha = self.commit[:7]
        self.source = f"ccf@{self.short_sha}"

    @classmethod
    def load(cls, path: Path | None = None) -> Factors:
        path = path or default_factors_dir() / FACTORS_FILE
        if not path.exists():
            raise FactorNotFound(f"factors file not found: {path}")
        return cls(json.loads(path.read_text(encoding="utf-8")), path.name)

    # ---- provenance ----------------------------------------------------------------------------

    @property
    def version(self) -> str:
        return self.commit

    def provenance(self, tier: Literal["vendored", "annual"] = "vendored") -> Provenance:
        return Provenance(source=self.source, version=self.commit, tier=tier)

    # ---- constants -----------------------------------------------------------------------------

    def constant(self, name: str) -> Sourced[float]:
        try:
            value = float(self._data["constants"][name])
        except KeyError as exc:
            raise FactorNotFound(f"constant {name!r} not in {self.file_name}") from exc
        return Sourced(value, self.provenance())

    def pue(self) -> Sourced[float]:
        return self.constant("pue")

    def replication(self, key: str) -> Sourced[int]:
        try:
            value = int(self._data["replication_factors"][key])
        except KeyError as exc:
            raise FactorNotFound(f"replication factor {key!r} not in {self.file_name}") from exc
        return Sourced(value, self.provenance())

    # ---- processors and instances --------------------------------------------------------------

    def processor(self, name: str) -> Sourced[tuple[float, float, str]]:
        try:
            p = self._data["processors"][name]
        except KeyError as exc:
            raise FactorNotFound(f"processor {name!r} not in {self.file_name}") from exc
        return Sourced((float(p["min_watts"]), float(p["max_watts"]), p["kind"]), self.provenance())

    def processor_watts(self, names: list[str] | tuple[str, ...]) -> Sourced[tuple[float, float]]:
        """Average min and max watts over several processors, as CCF does."""
        if not names:
            raise FactorNotFound("no processors given")
        mins, maxs = [], []
        for name in names:
            lo, hi, _ = self.processor(name).value
            mins.append(lo)
            maxs.append(hi)
        return Sourced((sum(mins) / len(mins), sum(maxs) / len(maxs)), self.provenance())

    def has_instance(self, instance_type: str) -> bool:
        return instance_type in self._data["instance_types"]

    def instance_types(self) -> list[str]:
        return sorted(self._data["instance_types"])

    def instance(self, instance_type: str) -> Sourced[InstanceSpec]:
        try:
            raw = self._data["instance_types"][instance_type]
        except KeyError as exc:
            raise FactorNotFound(
                f"instance type {instance_type!r} not in {self.file_name}"
            ) from exc
        processors = tuple(raw["cpu"])
        lo, hi = self.processor_watts(processors).value
        gpu = raw.get("gpu")
        gpu_count = 0
        if gpu:
            if "gpu_count" not in raw:
                raise FactorNotFound(f"instance type {instance_type!r} has a GPU but no gpu_count")
            gpu_count = int(raw["gpu_count"])
        gpu_lo = gpu_hi = 0.0
        if gpu:
            gpu_lo, gpu_hi, _ = self.processor(gpu).value
        arch: Literal["x86_64", "arm64"] = (
            "arm64" if all(p.startswith(GRAVITON_PREFIX) for p in processors) else "x86_64"
        )
        spec = InstanceSpec(
            instance_type=instance_type,
            vcpu=int(raw["vcpu"]),
            memory_gib=float(raw["memory_gib"]),
            processors=processors,
            min_watts_per_vcpu=lo,
            max_watts_per_vcpu=hi,
            gpu=gpu,
            gpu_count=gpu_count,
            gpu_min_watts=gpu_lo,
            gpu_max_watts=gpu_hi,
            arch=arch,
        )
        return Sourced(spec, self.provenance())

    # ---- regions -------------------------------------------------------------------------------

    def region_g_per_kwh(self, region: str) -> Sourced[float]:
        """Annual grid intensity (tier `annual`). `unknown` is not accepted as a fallback."""
        if region == "unknown":
            raise FactorNotFound("region 'unknown' is not a real region; refusing to default")
        try:
            value = float(self._data["regions"][region]["g_per_kwh"])
        except KeyError as exc:
            raise FactorNotFound(f"region {region!r} not in {self.file_name}") from exc
        return Sourced(value, self.provenance("annual"))

    def has_region(self, region: str) -> bool:
        return region != "unknown" and region in self._data["regions"]


@lru_cache(maxsize=4)
def load_default() -> Factors:
    return Factors.load()
