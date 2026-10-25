---
name: milestone
description: Implement one EmissionGate milestone end to end — plan, tests first for core, implement, prove each acceptance criterion, invariant review. Use only when the user names a milestone such as M3 or M1.5 (docs/BUILD_PLAN.md) or a phase such as E1 (docs/ENTERPRISE_READINESS.md).
---

# Implement a milestone

The user names the milestone: M0–M11 or M1.5 from `docs/BUILD_PLAN.md`, or a phase E0–E12 from
`docs/ENTERPRISE_READINESS.md`. If they did not, ask which one before doing anything. For an `E<n>` phase,
read "milestone section" below as that phase's section, "acceptance criteria" as its **Done when**, and
"every earlier milestone on the critical path" as the phases before it in that file's "Order of work"
diagram.

1. Read that milestone's section. Confirm every earlier milestone on the critical path is ticked; if one
   isn't, stop and say which. An E-phase may start while an earlier phase waits only on human-run steps
   (legal review, ADR acceptance, network); say which steps are outstanding.
2. Read the docs the section points to (usually DATA_CONTRACTS, METHODOLOGY, INTERVENTIONS,
   SYNTHETIC_ESTATE, ARCHITECTURE, THREAT_MODEL) and the ADRs it touches. Re-read the invariants in
   `AGENTS.md`, and the nested `AGENTS.md` for any package you will edit (`src/emissiongate/core/`,
   `src/emissiongate/llm/`).
3. Write a short plan: files to create or change, tests to add, and how each acceptance criterion will be
   demonstrated. Show it and wait for the user to agree before writing code.
4. For anything in `src/emissiongate/core/`, write the tests first with hand-checkable numbers (golden
   values from METHODOLOGY §6 where they apply). For an E1 control, write its test in `tests/security/`
   first.
5. Implement. Keep agents thin; push pure logic into `core/`.
6. Run `make lint test`. Fix until green. Run `tofu`-marked tests if the binary and `.tofu-providers/`
   mirror are present; if the mirror is missing, ask the human to run `make providers`.
7. Demonstrate each acceptance criterion with a command and its output. If a criterion needs network, the
   local Ollama server, a GitHub organisation, signing keys or legal sign-off, give the human the exact
   step and wait for the result.
8. Get a cold review. In Codex, run `make codex-review` (a separate `codex review` process driven by
   `docs/review/invariant-reviewer.md`; it does not modify the working tree); spawning the `invariant_reviewer` agent is a quicker alternative.
   In Claude Code, use the `invariant-reviewer` subagent. Fix every finding.
9. Tick the milestone box (and each completed item's box for an E-phase). If a decision changed, add an
   ADR.
10. Propose commit(s) with messages that say why. The human approves them.
11. Summarise: what was built, what is left, and anything that deviates from the docs and why.
