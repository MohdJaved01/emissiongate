# ADR-0020: Invariants for customer data, CI egress and short-lived credentials

- Status: accepted (2026-11-19, by the maintainer)
- Date: 2026-10-25
- Amends: the invariants in `AGENTS.md` (3, 10, 12, 13 and 14); applied on 2026-11-19

## Context

The invariants in `AGENTS.md` assume synthetic data and a laptop. Under ADR-0018 the engine runs on
customer runners against customer repositories and, under ADR-0019, customer-staged telemetry. Some
invariants would forbid that use; others need sharper wording to stay enforceable. AGENTS.md is changed
only after this ADR is accepted.

## Decision

The new wording, to be copied into `AGENTS.md` on acceptance:

- **3 — no capability to change infrastructure.** Unchanged. Telemetry is read per ADR-0019.
- **10 — offline.** "Offline mode always works with no network, no LLM and no GitHub token. The gate
  runs with network egress blocked except to the declared SCM API; OpenTofu providers come from the
  local mirror and nothing in a run downloads anything." The offline demo is unchanged.
- **12 — data.** "Customer data stays in the customer's boundary; nothing phones home. Demo and test
  data are synthetic and carry `synthetic: true`. Every published figure records its data origin
  (`synthetic` | `customer`). No real identifiers in this repository."
- **13 — secrets.** "Short-lived credentials only: the Actions token, OIDC federation and GitHub App
  installation tokens. Secrets never enter files an agent can read or write, logs, reports or ledger
  payloads."
- **14 — the gate informs.** Gains: "An acknowledgement is bound to the head commit and given by a user
  with write permission (E1); approval rules beyond that come from policy (E5)."
- **New — trusted inputs.** "In CI, policy, suppressions, factors, prices, telemetry and tool paths come
  only from trusted sources (action inputs, the base commit, an organisation config repository or the
  engine package), never from the pull request's tree." Proposed as invariant 15.

## Consequences

- The Code Review Rules gain a rule for invariant 15; `make agent-check` will require it.
- Invariant 12 no longer blocks running on real repositories, while the test and demo data rule stays.
- Until accepted, the current invariants apply, and new code satisfies both versions.
