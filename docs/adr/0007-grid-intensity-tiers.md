# ADR-0007: Grid intensity tiers: annual for totals, UK live/snapshot for time-shifting

- Status: accepted
- Date: 2026-09-28

## Context

Electricity Maps' free tier covers one zone with no forecast. Annual factors exist for every AWS region in the vendored CCF data. The UK Carbon Intensity API is free, keyless, half-hourly and has a 48h forecast (CC BY 4.0).

## Decision

Annual resource totals use the CCF regional annual factor everywhere, so regions compare on one basis. Half-hourly UK data (live, else committed snapshot) is used for `time_shift` decisions and savings in eu-west-2. Every figure is stamped with its tier.

## Consequences

Carbon-aware scheduling runs on real live data at zero cost. Time-shifting is only offered where half-hourly data exists.
