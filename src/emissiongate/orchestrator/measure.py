"""The agent's own energy via CodeCarbon (METHODOLOGY §5). Offline tracker: no network calls.

Labelled `measured` only when every non-zero component comes from hardware counters. CodeCarbon
models RAM power, so on most machines the total is `estimated`, with the measured CPU share stated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

MEASURED_CPU_MODES = {"intel_rapl", "intel_power_gadget", "apple_powermetrics", "windows_emi"}


@dataclass(frozen=True)
class Measurement:
    energy_kwh: float
    cpu_kwh: float
    ram_kwh: float
    gpu_kwh: float
    kg_co2e: float
    duration_s: float
    cpu_mode: str
    label: str  # measured | estimated
    tracking_method: str
    g_per_kwh: float
    grid_source: str


def describe(cpu_mode: str, cpu: float, ram: float, gpu: float, total: float) -> str:
    def share(x: float) -> str:
        return f"{x / total:.0%}" if total else "0%"

    how = "hardware counters" if cpu_mode in MEASURED_CPU_MODES else "TDP/model estimate"
    text = (
        f"codecarbon offline, tracking_mode=machine; CPU via {cpu_mode} ({how}, {share(cpu)} of "
        f"energy); RAM modelled by CodeCarbon ({share(ram)})"
    )
    if gpu:
        text += f"; GPU {share(gpu)}"
    return text


class Tracker:
    def __init__(self, country_iso: str) -> None:
        self.country_iso = country_iso
        self._tracker = None
        self.error: str | None = None

    def start(self) -> None:
        try:
            from codecarbon import OfflineEmissionsTracker

            logging.getLogger("codecarbon").setLevel(logging.ERROR)

            self._tracker = OfflineEmissionsTracker(
                country_iso_code=self.country_iso,
                tracking_mode="machine",
                save_to_file=False,
                log_level="error",
                measure_power_secs=1,
            )
            self._tracker.start()
        except Exception as exc:  # measurement must not break the run; it is reported as absent
            self.error = f"{type(exc).__name__}: {exc}"
            self._tracker = None

    def stop(self) -> Measurement | None:
        if self._tracker is None:
            return None
        try:
            kg = float(self._tracker.stop() or 0.0)
            d = self._tracker.final_emissions_data
            cpu_mode = "unknown"
            for hw in getattr(self._tracker, "_hardware", []):
                if type(hw).__name__ == "CPU":
                    cpu_mode = str(getattr(hw, "_mode", "unknown"))
            cpu, ram, gpu = float(d.cpu_energy), float(d.ram_energy), float(d.gpu_energy)
            total = float(d.energy_consumed)
            measured = cpu_mode in MEASURED_CPU_MODES and ram == 0 and gpu == 0
            return Measurement(
                energy_kwh=total,
                cpu_kwh=cpu,
                ram_kwh=ram,
                gpu_kwh=gpu,
                kg_co2e=kg,
                duration_s=float(d.duration),
                cpu_mode=cpu_mode,
                label="measured" if measured else "estimated",
                tracking_method=describe(cpu_mode, cpu, ram, gpu, total),
                g_per_kwh=kg / total * 1000 if total else 0.0,
                grid_source=f"CodeCarbon offline grid intensity for country {self.country_iso}",
            )
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            return None
