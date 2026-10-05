# ADR-0003: The agent has no capability to change infrastructure

- Status: accepted
- Date: 2026-09-28

## Context

The brief requires human approval for anything with financial, contractual, legal or reputational consequence. A prompt-level rule can be talked around; a missing capability cannot.

## Decision

No code path calls `tofu apply`/`destroy`, any AWS mutating API, or boto3. The only external write is a branch + PR in live mode. `.claude/settings.json` also denies these commands during development.

## Consequences

Oversight is structural. The demo shows a human merging; the agent cannot skip that step even when wrong.
