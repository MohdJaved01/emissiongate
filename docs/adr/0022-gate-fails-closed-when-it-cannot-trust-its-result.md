# ADR-0022: The gate fails closed when it cannot trust or read its own result

- Status: proposed
- Date: 2026-11-19
- Clarifies: invariant 14 (the gate fails a check only at a threshold) and invariant 6 (fail closed)

## Context

The gate is now two workflows (GATE §6): an unprivileged evaluate run and a privileged publish run that
sets the `EmissionGate / carbon` check. Organisations make that check required. GitHub counts `success`
and `neutral` as passing a required check, and a check run belongs to a commit, not a pull request.

Some outcomes have no carbon figure the publish step can trust:
- the evaluate artefact is missing or malformed, or is for another commit or repository;
- the pull request changes `.github/`, so its evaluate run used the PR's own workflow files;
- another open pull request with the same head commit targets another branch or changes `.github/`;
- the plan failed or the code was screened out ("not evaluated").

Invariant 14 says the gate fails a check only at a threshold in `policy.yaml → gate`. Read literally,
every case above would have to pass. That is the default-allow that invariant 6 forbids, and it would
make the check worthless as a required check.

## Decision

- "Not evaluated" follows the policy key `gate.not_evaluated_conclusion` (`failure` | `neutral`). The
  shipped policy says `failure`, a policy without the key fails, and any other value is an error. This
  makes it a configured threshold under invariant 14.
- An outcome the publish step cannot trust (the first three cases) fails the check, with a title saying
  why. It never claims a carbon result, and it is ledgered.
- When the pull request's head is no longer the evaluated commit, or cannot be confirmed, nothing is
  published. A newer run covers the new head, and a required check stays pending until then.
- An acknowledgement cannot pass any of these: it covers a carbon increase, not an untrusted result.

## Consequences

- Invariant 14 keeps its wording. This ADR records that a fail-closed refusal is not a carbon verdict
  and that "not evaluated" is governed by policy. On acceptance, AGENTS.md invariant 14 gains one clause
  pointing here.
- PRs that change `.github/`, including Dependabot action updates, fail the check. Maintainers merge
  them on their own, with a bypass or a separate ruleset.
- The demo estate's broken or screened PRs show a failing check instead of a neutral one.
