---
name: check-invariants
description: Review the current changes against the non-negotiable invariants in AGENTS.md. Use before finishing any task that touched src/, scripts/, policy.yaml or factors/.
---

Follow `.agents/skills/check-invariants/SKILL.md` exactly. It is the canonical version, shared with Codex; this file only points to it.

Claude Code differences: where it says "spawn the `invariant_reviewer` agent", use the `invariant-reviewer` subagent; where it says the human runs a command in their own terminal, ask them to — do not run network or live commands yourself.
