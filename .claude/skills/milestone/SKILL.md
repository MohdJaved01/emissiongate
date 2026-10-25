---
name: milestone
description: Implement one EmissionGate milestone (docs/BUILD_PLAN.md) or enterprise phase (docs/ENTERPRISE_READINESS.md) end to end. Use when the user names a milestone such as M3 or a phase such as E1.
disable-model-invocation: true
argument-hint: "[M0..M11, M1.5 or E0..E12]"
---

Follow `.agents/skills/milestone/SKILL.md` exactly. It is the canonical version, shared with Codex; this file only points to it.

Claude Code differences: where it says "spawn the `invariant_reviewer` agent", use the `invariant-reviewer` subagent; where it says the human runs a command in their own terminal, ask them to — do not run network or live commands yourself.

The milestone to implement: $ARGUMENTS
