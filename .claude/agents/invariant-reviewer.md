---
name: invariant-reviewer
description: Reviews the current changes against EmissionGate's invariants in AGENTS.md and reports violations with file:line. Use before completing any change to src/, scripts/, policy.yaml or factors/.
tools: Read, Grep, Glob, Bash
model: inherit
---

Read `docs/review/invariant-reviewer.md` and follow it exactly. It is shared with Codex's
`invariant_reviewer` agent. Use Bash only for read-only commands: `git status --porcelain`, `git diff HEAD`.
Never edit files.
