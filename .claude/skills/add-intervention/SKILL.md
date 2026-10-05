---
name: add-intervention
description: Add a new patch template consistently across contracts, core/patches, policy, savings, tests and docs. Use when asked to support a new kind of fix.
disable-model-invocation: true
argument-hint: "[template-name]"
---

Follow `.agents/skills/add-intervention/SKILL.md` exactly. It is the canonical version, shared with Codex; this file only points to it.

Claude Code differences: where it says "spawn the `invariant_reviewer` agent", use the `invariant-reviewer` subagent; where it says the human runs a command in their own terminal, ask them to — do not run network or live commands yourself.

The template to add: $ARGUMENTS
