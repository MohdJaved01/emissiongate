# ADR-0002: Plain Python state machine, no agent framework

- Status: accepted
- Date: 2026-09-28

## Context

The agent's own footprint is judged, which needs exact token and call accounting. Frameworks add hidden prompts and retries.

## Decision

Orchestration is an explicit run-level and candidate-level state machine with a JSON checkpoint written before each transition. No LangChain, LangGraph, CrewAI or similar.

## Consequences

Exact accounting, deterministic replay, resumable runs, fewer dependencies to declare. We write the ~300 lines of orchestration ourselves.
