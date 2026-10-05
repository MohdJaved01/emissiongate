# ADR-0009: Local runtime only; no cloud deployment, server or dashboard

- Status: accepted; amended by ADR-0015 (the PR gate runs in CI)
- Date: 2026-09-28

## Context

The agent's footprint is judged. A deployed demo adds idle, embodied-carbon-bearing infrastructure that must be declared. A dashboard recreates the 'report nobody acts on' problem.

## Decision

One CLI process on a laptop. Output is PRs plus a static HTML run report. The AWS production path (EventBridge, Step Functions, Lambda, S3) is described in the architecture, not built.

## Consequences

Smallest honest footprint; judges run it with one command. No live URL to show; the PR tab and the report fill that role.
