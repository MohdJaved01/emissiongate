# ADR-0008: Two repositories: the agent and the estate it changes

- Status: accepted
- Date: 2026-09-28

## Context

The agent opens PRs against infrastructure code. In one repo it would open PRs against itself.

## Decision

`emissiongate` holds the agent. `emissiongate-demo-estate` holds the generated Terraform and receives PRs in live mode.

## Consequences

Mirrors real use (the agent changes someone else's repo). The estate repo's PR tab becomes browsable evidence for judges without running anything.
