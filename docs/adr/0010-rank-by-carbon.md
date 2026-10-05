# ADR-0010: Rank by carbon, report cost alongside

- Status: accepted
- Date: 2026-09-28

## Context

Cost-ranked tools already exist. Ranking by cost and by carbon produces different orders (storage tiering vs Graviton).

## Decision

Candidates are ranked by annual kgCO2e saved. Cost is computed from synthetic prices and shown next to it, with both orders in the report.

## Consequences

The project answers 'isn't this just FinOps?' with evidence. Some high-cost-saving items rank low; that is the point.
