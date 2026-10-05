"""Grid-intensity tiers (METHODOLOGY §2, ADR-0007).

Annual resource totals always use the `annual` tier, so regions compare on one basis. The
`snapshot` tier (committed UK Carbon Intensity fixture) is used only where it changes a decision:
time-shifting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from emissiongate.contracts import Provenance
from emissiongate.core.factors import Factors, Sourced

SNAPSHOT_REGION = "eu-west-2"
SLOTS_PER_DAY = 48
HISTORY_SLOTS = 7 * SLOTS_PER_DAY


def annual_intensity(factors: Factors, region: str) -> Sourced[float]:
    return factors.region_g_per_kwh(region)


@dataclass(frozen=True)
class HalfHourSlot:
    start: datetime  # UTC
    g_per_kwh: float
    forecast: bool


@dataclass(frozen=True)
class GridSnapshot:
    region: str
    slots: tuple[HalfHourSlot, ...]
    provenance: Provenance

    def history(self) -> tuple[HalfHourSlot, ...]:
        """The most recent 7 days of half-hourly history."""
        return tuple(s for s in self.slots if not s.forecast)[-HISTORY_SLOTS:]

    def mean_by_slot_of_day(self) -> dict[int, float]:
        """7-day mean intensity per half-hour slot of the day (0..47), from history only."""
        sums: dict[int, float] = {}
        counts: dict[int, int] = {}
        for s in self.history():
            idx = s.start.hour * 2 + s.start.minute // 30
            sums[idx] = sums.get(idx, 0.0) + s.g_per_kwh
            counts[idx] = counts.get(idx, 0) + 1
        if len(sums) != SLOTS_PER_DAY:
            raise ValueError(f"snapshot covers {len(sums)} of {SLOTS_PER_DAY} half-hour slots")
        return {k: sums[k] / counts[k] for k in sorted(sums)}


def _utc(text: str) -> datetime:
    ts = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError(f"snapshot timestamp without offset: {text}")
    return ts.astimezone(UTC)


def parse_snapshot(doc: dict) -> GridSnapshot:
    """Parse a snapshot written by `emissiongate grid-snapshot` (fixtures/grid/uk_london_*.json)."""
    if doc.get("region") != SNAPSHOT_REGION:
        raise ValueError(f"snapshot region {doc.get('region')!r} is not {SNAPSHOT_REGION}")
    slots = []
    for row in doc["history"]:
        slots.append(HalfHourSlot(_utc(row["from"]), float(row["g_per_kwh"]), False))
    for row in doc.get("forecast", []):
        slots.append(HalfHourSlot(_utc(row["from"]), float(row["g_per_kwh"]), True))
    prov = Provenance(
        source=doc["source"],
        version=doc["retrieved_at"],
        tier="snapshot",
        retrieved_at=datetime.fromisoformat(doc["retrieved_at"]),
    )
    return GridSnapshot(
        region=doc["region"], slots=tuple(sorted(slots, key=lambda s: s.start)), provenance=prov
    )
