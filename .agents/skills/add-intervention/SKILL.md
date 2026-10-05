---
name: add-intervention
description: Add a new EmissionGate patch template (intervention type) consistently across contracts, core/patches, policy, savings, tests and docs. Use only when the user asks to support a new kind of fix and names it.
---

# Add an intervention

The user names the new template. If they did not, ask. A template touches six places — change all of
them in one commit or none.

1. `docs/DATA_CONTRACTS.md` and `src/emissiongate/contracts.py` — add the name to the `Intervention` literal.
2. `src/emissiongate/core/patches/<name>.py` — parameters with allowed values, a rule-based default, and a
   renderer returning complete new file contents. Follow an existing template's structure. Read
   `src/emissiongate/core/AGENTS.md` first.
3. Register it in `core/patches/registry.py`.
4. A savings function in `core/` following METHODOLOGY §3. Add the formula to METHODOLOGY §3 and a golden
   test computed from the vendored factors. No new coefficients unless they come from `factors/`.
5. `policy.yaml` — which environments and tags allow it; whether it is advisory-only.
6. Tests: default-parameter selection; a `tofu`-marked render test against the seed-42 estate (fmt,
   validate, plan with `-plugin-dir`); a policy test showing protected tags block it.
7. `docs/INTERVENTIONS.md` — a table row and a before/after HCL example.

If the new fix deletes resources or moves data between regions, it must be advisory-only (invariant 6).
Say so and stop rather than implementing it as a PR.
