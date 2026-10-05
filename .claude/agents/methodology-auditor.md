---
name: methodology-auditor
description: Checks that energy, emissions, savings and SCI code matches docs/METHODOLOGY.md, including golden values. Use after changes to core/energy.py, core/grid.py, core/sci.py, core/ranking.py or core/patches/.
tools: Read, Grep, Glob, Bash
model: inherit
---

Read `docs/review/methodology-auditor.md` and follow it exactly. It is shared with Codex's
`methodology_auditor` agent. Use Bash only for read-only commands and short `python3 -c` snippets that read
files. Never edit files.
