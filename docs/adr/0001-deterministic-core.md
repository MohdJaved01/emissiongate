# ADR-0001: The deterministic core computes every published number

- Status: accepted
- Date: 2026-09-28

## Context

Judges and users will challenge any carbon figure. LLMs produce plausible numbers that are not computed from anything.

## Decision

All energy, emissions, cost, ranking and savings figures are computed in `core/` from vendored factors. LLM outputs are limited to typed decisions, labels and prose. `core/` cannot import `llm/` or network code (enforced by test). PR bodies take numbers from templates; LLM prose goes into one slot and is discarded if it contains a numeric claim.

## Consequences

Every figure is reproducible and traceable. Offline mode is a complete baseline, which lets us measure what the LLM adds. The model cannot improve the numbers, only the choices and the explanation.
