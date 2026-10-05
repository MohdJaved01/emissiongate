---
name: score-run
description: Run the offline pipeline on seed 42 and report precision, recall, trap violations, carbon-vs-cost order and footprint.
---

Follow `.agents/skills/score-run/SKILL.md` exactly. It is the canonical version, shared with Codex; this file only points to it.

Claude Code differences: where it says "spawn the `invariant_reviewer` agent", use the `invariant-reviewer` subagent; where it says the human runs a command in their own terminal, ask them to — do not run network or live commands yourself.
