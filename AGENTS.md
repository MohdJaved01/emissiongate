# AGENTS.md — EmissionGate

Canonical instructions for coding agents. **Codex** reads this file directly (CLI, IDE, cloud, and
GitHub code review). **Claude Code** reads it through `CLAUDE.md`, which imports it. Change rules here,
not in tool-specific files. Keep this file under 24 KiB — Codex stops reading project instructions at
32 KiB combined (`make agent-check` enforces the budget).

## What this project is

EmissionGate has two modes on one engine. The **sweep** finds cloud and AI infrastructure waste that is
already running, quantifies it in kWh and kgCO2e per resource, and delivers the fix as a **reviewable pull
request** with the carbon delta, cost delta and evidence. The **gate** checks every pull request that
changes infrastructure code before merge and posts its carbon delta, with validated lower-carbon
suggestions (`docs/GATE.md`). Humans merge, reject or acknowledge. Rejections feed back as suppression rules.

Hackathon MVP. Judged on sustainability impact and measurability, agentic depth, **the agent's own
footprint**, demo quality and innovation. Every design choice serves one of those. All data is synthetic.
Track: Green IT (Green AI / AI energy efficiency + carbon accounting).

## Non-negotiable invariants

Violating any of these is a bug even if tests pass. Check every change against this list (skill
`check-invariants`, reviewer agent `invariant_reviewer`, and the Code Review Rules at the end).

1. **The LLM never produces a number that gets published.** Energy, emissions, cost, ranking and savings
   figures are computed in `src/emissiongate/core/`. LLM outputs are typed decisions (a template and
   parameter values from allowed lists), labels, or prose. If LLM prose contains a numeric carbon,
   energy or cost claim, it is discarded and replaced by the deterministic template.
2. **`core/` never imports `llm/`, `tools/`, `httpx`, `subprocess`, `socket` or any network code.** Pure
   functions plus reads of vendored data. Enforced by `tests/unit/test_architecture.py`.
3. **No capability to change infrastructure.** No code path calls `tofu apply`, `tofu destroy`,
   `terraform`, any AWS mutating API, or `boto3`. The only external write is a branch + PR in live mode.
4. **Every published figure carries provenance** — factor source + version, grid-intensity tier
   (`live` | `snapshot` | `annual`), and the ledger event id that produced it.
5. **Never invent emission factors, coefficients, grid intensities or prices.** Factors come only from
   `factors/*.json` (vendored with commit provenance) or a documented live API. Missing value → fail
   loudly or fall back to a documented tier. Synthetic prices exist only in the estate generator and are
   labelled synthetic.
6. **Fail closed on guardrails.** Protected tag, missing required tag, or unknown policy state → never a
   PR. `region_shift` and `decommission` are advisory-only.
7. **No PR draft without a passing `tofu validate` and `tofu plan`.** Repair attempts are capped at
   `max_repair_attempts` (3). When spent, escalate — never loop.
8. **The ledger is append-only and mandatory.** A failed ledger write fails the run. Every LLM call records
   model, reasoning level, prompt tokens, completion tokens (thinking included) and duration. Every tool
   call is recorded.
9. **Budgets are hard ceilings** (`policy.yaml → ceilings`). Hitting one stops cleanly at a checkpoint.
10. **Offline mode always works with no network, no LLM and no GitHub token.** OpenTofu providers come from
    the local mirror (`make providers`, then `tofu init -plugin-dir`); nothing in a run downloads anything.
11. **Measured vs estimated is never blurred.** If `codecarbon` falls back to a TDP estimate, the report says
    "estimated". Embodied carbon (M) is "not declared" unless the user configures it.
12. **All data is synthetic.** Generated artefacts carry `synthetic: true`. No real account IDs, customer
    names, client branding or real resource identifiers.
13. **Secrets never enter files an agent can read or write.** No tokens in code, fixtures, logs, reports,
    ledger payloads or `.env`. `GITHUB_TOKEN` is exported by a human in their own terminal for live mode.
14. **The gate informs; humans decide.** It never pushes to a PR branch, never merges, and fails a check only
    at a threshold in `policy.yaml → gate`. Passing an acknowledgement-required check needs a human label with
    a reason, recorded in the ledger. Assumed utilisation is always published as a range, labelled `assumed`.

## Architecture map

Diagrams: `docs/ARCHITECTURE.md`. Short version:

```
src/emissiongate/
  cli.py               typer app: estate | run | gate | score | sync-feedback | grid-snapshot | report | bakeoff
  config.py            env (.env) + policy.yaml + suppressions.yaml -> Settings
  contracts.py         pydantic v2 models — the interface between components (docs/DATA_CONTRACTS.md)
  orchestrator/        run-level + candidate-level state machines, checkpoint, budget
  agents/              planner, collector, diff_collector, quantifier, strategist, validator, reporter — thin
  core/                DETERMINISTIC: energy, factors, grid tiers, projection, policy, ranking, patches/, ledger, sci, scoring
  llm/                 LLM client protocol, Ollama client (structured output), prompts/ (jinja)
  tools/               side effects: cur (duckdb), metrics, tf (tofu subprocess), grid_uk (httpx), github (httpx)
  report/              run report (HTML) + PR body (markdown) templates
scripts/               generate_estate.py, check_agent_files.py, codex-cloud-install.sh
tofu/versions.tf       pinned provider constraint used by `make providers` and copied into the estate
factors/               vendored Cloud Carbon Footprint coefficients (never edit by hand)
fixtures/              grid snapshot (CC BY 4.0), llm_cases/ for the model bake-off
runs/<run_id>/         ledger.sqlite, checkpoint.json, manifest.json, report.html, prs/*.md,
                       prediction.json (gate runs) — all gitignored; predictions return via sync-feedback
```

Import direction: `cli -> orchestrator -> agents -> (core | llm | tools)`. `core` imports only
`contracts`, the standard library, pydantic and yaml. `llm` and `tools` never import `agents` or
`orchestrator`.

**Nested instructions.** `src/emissiongate/core/AGENTS.md` and `src/emissiongate/llm/AGENTS.md` add
rules for those packages. Codex loads nested files only when a session starts inside that directory, so
**read the nested file before editing anything under `core/` or `llm/`**, whichever tool you are.

## Modes

| Mode | Command | Needs | LLM | Writes PRs |
|---|---|---|---|---|
| offline | `make demo-offline` | Python 3.12, OpenTofu, provider mirror | no — rule-based choices, templated prose | drafts in `runs/<id>/prs/` |
| local | `make demo` | + Ollama with `gpt-oss:20b` (~14 GB) | yes, local | drafts in `runs/<id>/prs/` |
| live | `make demo-live` | + `GITHUB_TOKEN` exported, `EG_ESTATE_REPO` | yes, local | real PRs on the estate repo |
| gate | `make gate` locally · Actions on the estate repo | Python, OpenTofu, provider mirror | no | comment + check on a PR |

The LLM improves choices on ambiguous candidates, repairs plan failures and writes readable narrative.
Offline mode is a complete baseline; offline-vs-local differences (precision, first-attempt plan success,
energy, tokens) are a reported result.

## Commands

```bash
make setup           # venv + editable install + dev deps (network — human runs it)
make providers       # mirror OpenTofu providers into .tofu-providers/ (network — human runs it once)
make models          # ollama pull the configured models (network — human runs it)
make estate          # synthetic estate, seed 42 -> data/, .estate/, ground truth
make demo-offline    # estate + run --mode offline --approve   (no network)
make demo            # estate + run --mode local --approve     (needs local Ollama)
make demo-live       # human only: opens real PRs
make gate           # gate check of this branch vs BASE (default main); prints the PR comment
make score           # precision/recall vs ground truth for the latest run
make bakeoff         # model bake-off on fixtures/llm_cases (needs local Ollama)
make test            # pytest — never touches the network
make lint            # ruff check + ruff format --check
make fmt             # ruff format + ruff check --fix
make agent-check     # validates AGENTS.md, skills, .codex/ and .claude/ files stay consistent
make codex-review    # read-only Codex review of uncommitted changes against the invariants
```

Single test: `.venv/bin/pytest tests/unit/test_energy.py -k gpu -q`

## How to work in this repo

- Work milestone by milestone from `docs/BUILD_PLAN.md` — skill `milestone` (`$milestone M3` in Codex,
  `/milestone M3` in Claude Code). Do not start a milestone until the previous one's acceptance criteria pass.
- For anything in `core/`: write the test first with hand-checkable numbers. Golden values are in
  `docs/METHODOLOGY.md §6`; they must match to 3 decimal places.
- Keep agents thin. Logic that could be pure belongs in `core/`.
- New intervention type → skill `add-intervention`. It touches contracts, core/patches, policy,
  INTERVENTIONS.md and tests — all or none.
- Before finishing any task: `make lint test`, then the `check-invariants` skill.
- Changing a decision recorded in an ADR → write a new ADR that supersedes it. Don't edit history.
- Small commits whose messages say *why*. The commit history is evidence the work happened inside the
  hackathon window — never squash or rewrite it.
- **Augmentation log (a submission deliverable).** After each milestone, before asking the human to
  approve it, append one entry to `docs/augmentation-log.md` in the template given there: what was
  attempted, the output, accepted/modified/rejected, errors found and by whom, corrective steps,
  evidence. Name the tool honestly. Never invent or backdate an entry; record failures as they happened.
- Today's order and cut list: `docs/BUILD_PLAN.md` → "Submission scope". It overrides the milestone order.

## Sandbox and approvals (Codex)

- Default: workspace-write sandbox, **network off**, approval on request (`.codex/config.toml`).
  Everything in `make test`, `make lint`, `make estate`, `make demo-offline` and `make score` works
  inside it. If a step needs network or the local Ollama server, **stop and ask the human to run it** in
  their own terminal rather than requesting escalation — setup, provider mirroring, model pulls, local and
  live demos, grid snapshots and the bake-off are human-run.
- `.git/`, `.codex/` and `.agents/` are read-only inside the sandbox: commits and edits to agent
  configuration need approval. Propose the commit message; let the human approve.
- `.codex/rules/emissiongate.rules` forbids `tofu apply|destroy|import|state`, `terraform`, the AWS CLI and
  `make demo-live`. Never try to work around a forbidden rule.
- Energy for the report is measured on a human-run `make demo` outside any agent sandbox. Never run a
  measured demo inside Codex and never label sandboxed timings as measured energy.

## Conventions

- Python 3.12. Type hints everywhere; pydantic v2 models for anything crossing a component boundary.
- `ruff` for lint + format (line length 100). No `print()` outside `cli.py`; use `logging`; `rich` only
  in the CLI layer.
- Deterministic ordering: sort by stable keys before output; seed every random generator.
- Units in names: `kwh`, `kg_co2e`, `g_per_kwh`, `watts`, `hours`, `gib`, `tb`, `usd_synthetic`.
- Keep floats unrounded internally; round only in `report/`.
- Prompts live in `src/emissiongate/llm/prompts/*.j2`, never inline in Python.
- Model names and reasoning levels come from config (`EG_MODEL_*`, `EG_THINK_*`), never literals in code.

## LLM usage rules

- Default runtime model: **`gpt-oss:20b`** via Ollama — OpenAI's open-weight model, Apache-2.0 — one
  resident model with two reasoning levels: `EG_THINK_SMALL=low` (planning, classification, narrative) and
  `EG_THINK_LARGE=medium` (patch decision, parameter repair). Qwen models are the measured alternative;
  switch only on bake-off evidence (ADR-0013).
- Call Ollama `/api/chat` **non-streaming** with `format=<JSON schema>` and `think=<level>`. Read
  `message.content`; keep `message.thinking` out of prompts, reports and the ledger (hash it if needed).
  Strip Markdown code fences before parsing — gpt-oss sometimes wraps JSON despite `format`.
- Call sites, and only these: scan planning, ambiguous classification, patch decision, parameter repair
  from plan stderr, PR narrative.
- Validate every response against its pydantic schema. On failure: one re-ask with the schema and the
  validation error; then the deterministic path, logged as `kind=fallback`.
- Patch decisions choose from `core/patches` templates and allowed parameter values given in the prompt.
  The model never writes HCL.
- Always set `num_ctx` explicitly (`EG_NUM_CTX`). Decisions are deterministic where the model allows it
  (temperature 0); narrative ≤ 0.3.
- A hosted OpenAI-compatible fallback exists behind `EG_LLM_PROVIDER=openai_compat`, off by default.
  Using it forfeits the measured-energy claim; the report must say so.

## Testing rules

- Tests never touch the network. HTTP is mocked with `respx`; the UK grid API has recorded fixtures.
- Tests never call Ollama. LLM behaviour is tested with a `FakeLLMClient` returning canned JSON, including
  fenced JSON and numeric-claim narratives.
- `tofu` tests are marked `@pytest.mark.tofu`, use `-plugin-dir`, and skip if the binary or mirror is absent.
- `tests/ground_truth/` runs the offline pipeline on seed 42 and asserts zero PRs on traps, zero
  expiration/deletion on regulatory storage, and recall ≥ the threshold in `docs/SYNTHETIC_ESTATE.md`.

## Do not

- Add LangChain, LangGraph, CrewAI or any agent framework (ADR-0002).
- Add a web server, database server, dashboard or frontend (ADR-0009).
- Use PyGithub (LGPL) — GitHub is ~5 REST endpoints via httpx (ADR-0011).
- Use Terraform ≥ 1.6 (BUSL); the toolchain is OpenTofu (ADR-0006).
- Use Llama or Codestral models — licence restrictions (ADR-0004, ADR-0013).
- Call the Electricity Maps API by default (ADR-0007).
- "Fix" the trap resources in the synthetic estate; they exist to be refused.
- Claim savings for PRs that were not merged. Report `proposed` and `merged` separately.
- Edit `.agents/`, `.codex/` or `.claude/` unless the task is agent configuration; run `make agent-check` after.

## Glossary

- **Candidate** — a resource + intervention pair under consideration.
- **Intervention / patch template** — fixed, parameterised change type (`rightsize`, `schedule`,
  `graviton`, `storage_tier`, `time_shift`); see `docs/INTERVENTIONS.md`.
- **Advisory** — a finding that is never a PR (`region_shift`, `decommission`, guardrail hits).
- **Tier** — grid-intensity source: `live` (UK API), `snapshot` (committed fixture), `annual` (CCF factor).
- **Trap** — a seeded resource that looks like waste but must be refused.
- **SCI** — Software Carbon Intensity, ISO/IEC 21031:2024: `(E × I + M) / R`.
- **Gate 1 / Gate 2** — human scope approval before a run / human merge of a PR.
- **Reasoning level** — gpt-oss `think` setting (`low` | `medium` | `high`); our two "tiers".

## Where to look

| Question | File |
|---|---|
| Components, state machines, sequences | `docs/ARCHITECTURE.md` |
| Formulas, factor tiers, SCI, golden values | `docs/METHODOLOGY.md` |
| Every model/schema | `docs/DATA_CONTRACTS.md` |
| Intervention templates and their HCL | `docs/INTERVENTIONS.md` |
| Synthetic estate, traps, ground truth | `docs/SYNTHETIC_ESTATE.md` |
| PR gate behaviour, thresholds, security | `docs/GATE.md` |
| What to build next | `docs/BUILD_PLAN.md` |
| Tool setup: Codex, Claude Code, sandbox, cloud, reviews | `docs/DEVELOPING.md` |
| Reviewer instructions | `docs/review/` |
| Why a decision was made | `docs/adr/` |
| Licences and borrowed components | `THIRD_PARTY.md` |

## Code Review Rules

Used by Codex code review on GitHub (`@codex review`) and by local reviews. Flag these as P0/P1; each
rule gives the safe path. More specific rules live in `src/emissiongate/core/AGENTS.md` and
`src/emissiongate/llm/AGENTS.md`.

- **Numbers from the model (P0, invariant 1).** Flag any carbon, energy, cost, ranking or savings figure
  that reaches a report, PR body or ledger from LLM output. Safe path: compute in `core/`, insert via template.
- **Core purity (P0, invariant 2).** Flag imports of `llm`, `tools`, `httpx`, `subprocess`, `socket` or
  `urllib` under `src/emissiongate/core/`. Safe path: pass data in from `agents/`.
- **Infrastructure change capability (P0, invariant 3).** Flag `apply`, `destroy`, `import`, state
  commands, boto3 or AWS CLI calls anywhere in `src/` or `scripts/`. Safe path: plan-only validation.
- **Missing provenance (P1, invariant 4).** Flag figures without factor version, tier or ledger event id.
- **Invented values (P1, invariant 5).** Flag literal coefficients, intensities or prices outside
  `factors/` and the estate generator. Safe path: load from the factors file; add new data with provenance.
- **Default-allow guardrails (P0, invariant 6).** Flag policy checks that allow on unknown or missing input,
  or a PR path for `region_shift`/`decommission`.
- **Unvalidated or unbounded repair (P1, invariant 7).** Flag PR drafts created without a successful plan, or
  repair loops without the `max_repair_attempts` ceiling.
- **Unledgered calls (P1, invariant 8).** Flag LLM or tool calls that bypass the ledger, or LLM calls without
  token counts and reasoning level.
- **Ceiling bypass (P1, invariant 9).** Flag code that ignores `policy.yaml → ceilings`.
- **Network in tests or offline mode (P1, invariant 10).** Flag tests without mocks, or `tofu init` without
  `-plugin-dir`.
- **Measured vs estimated (P1, invariant 11).** Flag "measured" in reports without checking the codecarbon
  tracking method.
- **Real data (P0, invariant 12).** Flag real-looking account IDs, ARNs, customer or client names.
- **Gate overreach (P0, invariant 14).** Flag gate code that writes to a PR branch, merges, approves, fails a
  check outside the configured thresholds, accepts without the label and a reason, or publishes an assumed
  figure without its range and label. Safe path: comment, set the job result, record in the ledger.
- **Secrets (P0, invariant 13).** Flag tokens or keys in code, fixtures, logs, reports, `.env.example`
  values, or ledger payloads.
