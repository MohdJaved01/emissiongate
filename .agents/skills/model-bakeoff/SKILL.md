---
name: model-bakeoff
description: Compare candidate local LLMs for EmissionGate on schema validity, decision agreement, tokens, latency and energy, and recommend the runtime model per ADR-0013. Use when choosing or re-checking the runtime model.
---

# Model bake-off

The bake-off needs the local Ollama server, which the Codex sandbox cannot reach. The human runs it.

1. Check `fixtures/llm_cases/` has the cases described in `docs/BUILD_PLAN.md` (M1.5). If not, build
   them first.
2. Ask the human to run, in their own terminal: `make bakeoff` (models from `EG_BAKEOFF_MODELS`).
3. Read the newest `runs/bakeoff/*.json` and present one table: model, think level, schema-valid on first
   try, valid after re-ask, decision agreement, tokens (thinking included), median latency, energy and its
   label (measured/estimated).
4. Apply the decision rule from ADR-0013: among models with ≥ 95% first-try schema validity and ≥ 90%
   decision agreement, choose the lowest energy per case. If none qualifies, keep offline behaviour as the
   default and say so.
5. If the rule picks a different model than `.env.example`, propose the two-line config change and an
   "Outcome" note appended to ADR-0013 with the table. The human approves.
