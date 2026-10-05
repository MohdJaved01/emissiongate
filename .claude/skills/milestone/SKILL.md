---
name: milestone
description: Implement one EmissionGate milestone from docs/BUILD_PLAN.md end to end. Use when the user names a milestone such as M3.
disable-model-invocation: true
argument-hint: "[M0..M11 or M1.5]"
---

Follow `.agents/skills/milestone/SKILL.md` exactly. It is the canonical version, shared with Codex; this file only points to it.

Claude Code differences: where it says "spawn the `invariant_reviewer` agent", use the `invariant-reviewer` subagent; where it says the human runs a command in their own terminal, ask them to — do not run network or live commands yourself.

The milestone to implement: $ARGUMENTS
