# ADR-0018: Customer-run plugin — CLI, image, GitHub Action and plan-JSON mode; no hosted service in v1

- Status: proposed
- Date: 2026-10-25
- Amends: ADR-0009 (local runtime only), ADR-0015 (PR gate in CI)

## Context

The hackathon build runs as a CLI on a laptop (sweep) and as a job in the infrastructure repository's CI
(gate). To be adopted by organisations it must install cleanly, run on their own repositories and fit
their pipelines. A hosted service would be quicker to try but would take customer code, plans, billing
and telemetry outside the customer's boundary, and would bring service certification (SOC 2 or ISO
27001), a hosting DPA, a subprocessor list and on-call into scope. See
[ENTERPRISE_READINESS.md](../ENTERPRISE_READINESS.md), "What plugin means here".

## Decision

- v1 is **customer-run only**. There is no EmissionGate server. The engine ships as a PyPI package, a
  signed container image and a GitHub Action that runs the image by digest.
- **Plan-JSON mode is the default for real repositories.** The customer's existing plan job, which has
  real state, modules, data sources and credentials, produces `tofu show -json` or
  `terraform show -json`; the gate reads that file and never executes the pull request's code.
- **Sandboxed planning** (today's mode) stays for repositories without a plan job, under the E1 controls.
- GitHub.com and GHES come first. Other SCMs and an optional self-hosted GitHub App are 2.0 (E12).
- A vendor-hosted service is out of scope for v1 and needs its own ADR and pilot evidence.

## Consequences

- Customer data never leaves the customer's boundary, so the compliance scope stays small.
- ADR-0009's "no server" still holds; its "laptop only" does not: the engine runs on customer runners.
- The gate must be safe on untrusted pull requests (E1) before it can be a required check.
- Plan-JSON mode removes most of the plan-time attack surface but trusts the customer's plan job; the
  threat model records that boundary.
- Support costs move to documentation, recipes and release verification rather than operating a
  service.
