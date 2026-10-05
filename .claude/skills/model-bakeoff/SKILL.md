---
name: model-bakeoff
description: Compare candidate local LLMs on schema validity, decision agreement, tokens, latency and energy, and recommend the runtime model per ADR-0013.
disable-model-invocation: true
---

Follow `.agents/skills/model-bakeoff/SKILL.md` exactly. It is the canonical version, shared with Codex; this file only points to it.

Claude Code differences: where it says "spawn the `invariant_reviewer` agent", use the `invariant-reviewer` subagent; where it says the human runs a command in their own terminal, ask them to — do not run network or live commands yourself.
