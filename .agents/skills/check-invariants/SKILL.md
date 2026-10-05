---
name: check-invariants
description: Review the current changes against the non-negotiable invariants in AGENTS.md before finishing a task. Use whenever code under src/, scripts/, policy.yaml or factors/ has changed.
---

# Check invariants

1. Get a cold review that follows `docs/review/invariant-reviewer.md`:
   - Codex: `make codex-review` — a separate `codex review` process driven by
     `docs/review/invariant-reviewer.md`; it does not modify the working tree. Spawning the `invariant_reviewer` agent also works; if its reply doesn't show it read
     `docs/review/invariant-reviewer.md`, its definition didn't load — use `make codex-review` instead.
   - Claude Code: the `invariant-reviewer` subagent.
2. Independently run these checks and inspect every hit:
   - `.venv/bin/pytest tests/unit/test_architecture.py -q` — core must not import llm/tools/network code.
   - `grep -rnE "tofu (apply|destroy|import|state)|terraform |boto3|aws " src/ scripts/` — must return nothing
     (comments and docstrings that forbid these are fine).
   - `grep -rnE "[0-9]+\.[0-9]+ *(#.*)?(kg|kwh|g_per_kwh|watts)" src/emissiongate --include=*.py` —
     a literal coefficient outside the factors loader violates invariant 5.
   - `grep -rniE "(ghp_|github_pat_|sk-[A-Za-z0-9]{10,}|api[_-]?key *= *['\"][^'\"]+)" src/ scripts/ fixtures/` —
     any hit violates invariant 13.
3. Fix everything found before reporting the task as done.
4. If an invariant itself must change, stop and say so. That needs a human decision and a new ADR.
