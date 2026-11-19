# ADR-0019: Telemetry and billing are read from customer-staged exports in v1

- Status: accepted (2026-11-19, by the maintainer)
- Date: 2026-10-25
- Related: ADR-0003 (no capability to change infrastructure), ADR-0018

## Context

The sweep and the gate need utilisation and billing data. Today both read synthetic files written by the
estate generator. On real estates there are two ways to get the data:

1. The customer exports it to storage they control (AWS Data Exports / CUR 2.0, FOCUS exports,
   CloudWatch or Prometheus summaries) and EmissionGate reads files.
2. EmissionGate calls provider APIs with a read-only role.

Option 2 puts cloud credentials and an SDK inside the engine. Even a read-only policy is easy to widen by
mistake, and ADR-0003 rules out any client that could mutate infrastructure (`boto3` is banned
outright).

## Decision

- v1 reads **files only**: billing and utilisation exports that the customer stages in storage they
  control, fetched by their own pipeline step with their own credentials, then passed to EmissionGate as
  a directory.
- EmissionGate ships documented schemas for these inputs and a validator; a file that does not match
  fails closed (the resource is "not quantified").
- Every figure records its data origin (`synthetic` | `customer`) in provenance.
- A read-only API reader is deferred. If a later ADR adds one, it uses an allowlist of API actions,
  ships a least-privilege IAM policy validated with IAM Access Analyzer, uses OIDC federation and never
  `boto3` (ADR-0003 stands).

## Consequences

- Invariant 3 stays as written: no code path in EmissionGate holds cloud credentials.
- Customers do one extra pipeline step to stage data; the recipes in E2 and E11 show it.
- The gate's observed-utilisation path reads a trusted, customer-staged summary instead of files in the
  pull request's tree (E1 trusted configuration).
