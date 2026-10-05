"""SCI of a run: (E × I + M) / R (ISO/IEC 21031:2024, METHODOLOGY §5)."""

from __future__ import annotations

from typing import Literal

from emissiongate.contracts import SciResult

SECONDS_PER_YEAR = 31_536_000


def sci(
    energy_kwh: float,
    energy_label: Literal["measured", "estimated"],
    tracking_method: str,
    grid_g_per_kwh: float,
    grid_source: str,
    run_seconds: float,
    device_embodied_kg: float | None,
    device_lifespan_years: float,
    proposed_kg_yr: float,
    merged_kg_yr: float | None,
    accepted_recommendations: int,
) -> SciResult:
    """M is `None` (not declared) unless the user configured the device's embodied carbon."""
    embodied = None
    if device_embodied_kg is not None:
        embodied = device_embodied_kg * run_seconds / (device_lifespan_years * SECONDS_PER_YEAR)
    per_run = energy_kwh * grid_g_per_kwh / 1000.0 + (embodied or 0.0)
    return SciResult(
        energy_kwh=energy_kwh,
        energy_label=energy_label,
        tracking_method=tracking_method,
        grid_g_per_kwh=grid_g_per_kwh,
        grid_source=grid_source,
        embodied_kg_co2e=embodied,
        kg_co2e_per_run=per_run,
        kg_co2e_per_accepted_recommendation=(
            per_run / accepted_recommendations if accepted_recommendations else None
        ),
        payback_ratio_merged=(merged_kg_yr / per_run if merged_kg_yr and per_run else None),
        payback_ratio_proposed=(proposed_kg_yr / per_run if per_run else None),
    )
