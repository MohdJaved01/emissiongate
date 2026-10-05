# ADR-0012: AGENTS.md is canonical; Codex is the primary development tool

- Status: accepted; the primary-tool decision is amended by ADR-0016 for the submission build
- Date: 2026-09-30

## Context

EmissionGate is being built for the Nagarro × OpenAI Codex hackathon, and team members may use different
coding agents. Keeping `CLAUDE.md` and a separate Codex file in sync by hand would let the invariants drift
apart, and the invariants are what keep the published numbers honest.

## Decision

`AGENTS.md` is the single source of agent instructions and code-review rules. Codex reads it natively and
uses its `## Code Review Rules` section for GitHub reviews. Codex-specific configuration lives in `.codex/`
(project config, command rules, custom agents) and `.agents/skills/`. Claude Code keeps working through
`CLAUDE.md`, which imports `AGENTS.md`, and thin pointer files in `.claude/`. Reviewer instructions live
once in `docs/review/`. `make agent-check` runs in CI and fails on drift.

## Consequences

One place to change a rule; the same rules drive local work and pull-request review. Tool differences —
nested-file loading, argument passing, permission syntax — are documented in `docs/DEVELOPING.md`. Claude
Code's "deny reading `.env`" has no Codex equivalent, so secrets are kept out of files altogether
(invariant 13).
