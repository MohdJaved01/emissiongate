# ADR-0021: Support matrix, compatibility contract and v1 targets

- Status: accepted (2026-11-19, by the maintainer)
- Date: 2026-10-25

## Context

Organisations that make the gate a required check need to know what it runs on, what may change between
releases and what quality bar each release meets. ENTERPRISE_READINESS.md uses targets marked
*proposed*; this ADR fixes them.

## Decision

**Support matrix (v1).**

| Area | Supported |
|---|---|
| SCM | GitHub.com; GHES — the oldest release still in GitHub's support window at 1.0 |
| Runners | Linux amd64 and arm64 |
| Python (CLI install) | 3.12 and 3.13 |
| IaC input | OpenTofu ≥ 1.8 plans and configurations; Terraform plan JSON (input only; the Terraform CLI is never run, ADR-0006) |
| Cloud | AWS first |

**Compatibility contract.** Semantic versioning covers: CLI commands and flags, configuration and policy
schemas, exit codes, the comment marker (`<!-- emissiongate-gate -->`), the check-run name
(`EmissionGate / carbon`), the ledger and evidence schemas, and `GatePrediction`. A removal is preceded
by one minor release that emits deprecation warnings. Before 1.0, minor releases may break these with a
changelog entry.

**Targets.**

| Target | Value |
|---|---|
| Quantified share of changed EC2, ASG, RDS and EBS resources on the corpus (E3) | ≥ 90% |
| Instance-type coverage of factors on the corpus (E4) | ≥ 95% |
| Gate p95 runtime on the reference repository (E9) | ≤ 60 s |
| OpenSSF Scorecard (E7) | ≥ 8/10 |
| Fix time for a critical / high vulnerability (E7) | 7 / 30 days |
| Test coverage floor enforced in CI | 80% line coverage of `src/emissiongate` |

## Consequences

- The comment marker and exit codes are frozen now; changing them needs a deprecation cycle.
- Coverage and performance targets become CI-enforced as each phase adds its measurement.
