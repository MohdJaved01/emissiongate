"""Hourly series -> `Utilisation` (35-day window, min datapoints, weekly activity mask).

An hour is *active* when the resource serves requests (if a request series exists) or, otherwise,
when it is running above the idle CPU threshold. The hour-of-week mask (Monday 00:00 UTC first)
marks hours active in at least half of the observed weeks. A schedule is only safe when the mask
covers the activity: `mask_coverage` is the share of active hours inside the mask.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from emissiongate.contracts import Utilisation

HOURS_PER_WEEK = 168
MASK_MAJORITY = 0.5
WEEK_AGREEMENT = 0.9


def hour_of_week(ts: datetime) -> int:
    return ts.weekday() * 24 + ts.hour


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(0.95 * len(ordered)) - 1))
    return ordered[rank]


def _weighted_mean(values: list[float], weights: list[int]) -> float | None:
    total = sum(weights)
    if total == 0:
        return None
    return sum(v * w for v, w in zip(values, weights, strict=True)) / total


def summarise(
    resource_id: str,
    start: datetime,
    running: list[int] | None,
    cpu: list[float | None] | None,
    gpu: list[float | None] | None,
    requests: list[int] | None,
    window_days: int,
    min_datapoints: int,
    idle_cpu: float,
) -> Utilisation:
    if running is None or cpu is None:
        return Utilisation(
            resource_id=resource_id,
            window_days=window_days,
            datapoints=0,
            sufficient=True,
            reason="storage: compute utilisation not applicable",
        )
    n = len(running)
    if n < min_datapoints:
        return Utilisation(
            resource_id=resource_id,
            window_days=window_days,
            datapoints=n,
            sufficient=False,
            reason=f"{n} hourly datapoints < min_datapoints {min_datapoints}",
        )
    times = [start + timedelta(hours=i) for i in range(n)]
    up = [i for i in range(n) if running[i] > 0 and cpu[i] is not None]
    weights = [running[i] for i in up]
    cpu_up = [float(cpu[i]) for i in up]  # type: ignore[arg-type]
    cpu_avg = _weighted_mean(cpu_up, weights)
    gpu_avg = None
    if gpu is not None:
        gpu_avg = _weighted_mean([float(gpu[i]) for i in up], weights)  # type: ignore[arg-type]

    if requests is not None:
        active = [requests[i] > 0 for i in range(n)]
    else:
        active = [running[i] > 0 and (cpu[i] or 0.0) > idle_cpu for i in range(n)]

    seen = [0] * HOURS_PER_WEEK
    hits = [0] * HOURS_PER_WEEK
    for i, ts in enumerate(times):
        k = hour_of_week(ts)
        seen[k] += 1
        hits[k] += active[i]
    mask = [seen[k] > 0 and hits[k] / seen[k] >= MASK_MAJORITY for k in range(HOURS_PER_WEEK)]

    n_active = sum(active)
    inside = sum(1 for i in range(n) if active[i] and mask[hour_of_week(times[i])])
    coverage = inside / n_active if n_active else None

    weeks: dict[int, list[int]] = {}
    origin = start - timedelta(hours=hour_of_week(start))
    for i, ts in enumerate(times):
        weeks.setdefault(int((ts - origin).total_seconds() // (HOURS_PER_WEEK * 3600)), []).append(
            i
        )
    matching = 0
    for idx in weeks.values():
        agree = sum(1 for i in idx if active[i] == mask[hour_of_week(times[i])])
        outside = any(active[i] and not mask[hour_of_week(times[i])] for i in idx)
        if agree / len(idx) >= WEEK_AGREEMENT and not outside:
            matching += 1
    regularity = matching / len(weeks)

    off = [j for j, i in enumerate(up) if not mask[hour_of_week(times[i])]]
    cpu_off = _weighted_mean([cpu_up[j] for j in off], [weights[j] for j in off])
    gpu_off = None
    if gpu is not None and off:
        gpu_off = _weighted_mean(
            [float(gpu[up[j]]) for j in off],  # type: ignore[arg-type]
            [weights[j] for j in off],
        )
    return Utilisation(
        resource_id=resource_id,
        window_days=window_days,
        datapoints=n,
        cpu_avg=cpu_avg,
        cpu_p95=p95(cpu_up) if cpu_up else None,
        gpu_avg=gpu_avg,
        active_hour_share=n_active / n,
        active_mask_168=mask,
        sufficient=True,
        running_hour_share=len(up) / n,
        cpu_avg_off_mask=cpu_off,
        gpu_avg_off_mask=gpu_off,
        weekly_regularity=regularity,
        mask_coverage=coverage,
    )
