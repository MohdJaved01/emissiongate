# ADR-0015: PR gate runs in CI on the infrastructure repo, deterministic, human-acknowledged

- Status: accepted
- Date: 2026-10-01
- Amends: ADR-0009 (the sweep still runs locally; the gate runs in CI)

## Context

The pitch is "carbon at merge time", but the sweep only acts on infrastructure that is already running.
Without a check on pull requests, new waste is merged unseen and found weeks later. A PR check must run
where PRs are reviewed — in the infrastructure repo's CI — and must not slow reviews or add a large
footprint of its own.

## Decision

`emissiongate gate` runs as a GitHub Actions job on every PR that changes `*.tf` in the infrastructure
repo. It plans base and head offline from the provider mirror, projects energy and emissions per changed
resource (observed utilisation where telemetry exists, a stated assumption band where it doesn't), posts
one sticky comment with deltas and validated lower-carbon suggestions, and sets the job result from
`policy.yaml → gate` thresholds. Above the acknowledgement threshold the job fails until a human adds
`eg/carbon-accepted` with a reason. No LLM runs in CI. The gate never pushes to the branch or merges.

## Consequences

- The thesis is demonstrable on any PR, including the sweep's own fix PRs.
- ADR-0009's "nothing deployed" no longer holds absolutely: the gate costs CI seconds per PR, reported in
  its comment footer as estimated energy (hosted runners expose no hardware counters).
- Projections for new resources rest on an assumption (CCF's 50% default). It is always shown as a range,
  and the sweep later calibrates it against observed utilisation.
- Only the vetted AWS provider is available to `tofu init`, so untrusted PR code cannot run programs at
  plan time through other providers.
