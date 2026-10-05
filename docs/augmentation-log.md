# Augmentation log — how AI was used to build EmissionGate

This log records every significant use of AI across the software lifecycle: what was attempted, what the
human accepted, modified or rejected, which errors were found (by the AI, by the human, or by tests),
and what was done about them. Entries name the tool that did the work. Items marked **planned** are not
claimed until their evidence column is filled.

**Tools**

| Tool | Where | Role |
|---|---|---|
| Claude Code (VS Code extension, Opus) | personal laptop, native Windows 11, 32 GB (ADR-0017) | all code in this repository, M0 onwards |
| OpenAI Codex (CLI) under `AGENTS.md` and `.codex/` | work laptop, Windows | M0 scaffold prototype and checks (not in this repository's history); optional read-only reviews |
| Claude (claude.ai) | browser | ideation, architecture, methodology, documentation, design reviews |

**Rules every AI worked under** (enforced in [AGENTS.md](../AGENTS.md), `.codex/rules/`, `.claude/settings.json`)

- No `tofu apply/destroy/import/state`, `terraform`, AWS CLI or live-mode demo — forbidden by command rules.
- Every published number comes from deterministic code; LLM output may not contain figures (tested).
- Network is off in the coding agent's sandbox; a human runs installs, provider downloads and pushes.
- A human approves each milestone before it is ticked in [BUILD_PLAN.md](BUILD_PLAN.md).
- Each milestone is checked by a separate reviewer agent before a human approves it.

---

## Codex across the lifecycle

**Why Codex's role is limited.** Codex licences were provided late in the hackathon window
(on <DATE LICENCES ARRIVED>). Codex built and checked an M0 scaffold on a Windows work laptop on
4–5 October. With the submission due on 5 October, that machine lacking a Linux toolchain and having too
little memory for the local model, the submission was built from scratch with Claude Code
([ADR-0016](adr/0016-claude-code-builds-submission.md)). The repository stays Codex-ready: the
instructions, sandbox, rules, skills and reviewers below are what a Codex session starts from.

### What Codex did

1. **Implementation — built an M0 scaffold prototype** from `$milestone M0` (kept on the work laptop, not
   in this repository): package layout, the typer CLI with
   stub commands, and the architecture test that fails the build if `core/` imports the LLM, network or
   subprocess code. This test is the guard for the project's main trust boundary.
2. **Verification — checked its own work before reporting done:** Python compilation, a core-import
   architecture scan, agent-file consistency, a dangerous-capability scan (no apply/destroy paths), a
   literal-coefficient scan (no hard-coded emission factors), a secret scan, and a cold invariant review in
   a separate reviewer context. Result: no violations.
3. **Environment bring-up:** installed the Python dependencies and OpenTofu, built the local provider
   mirror, fixed the lint and format findings, and got 32 tests passing with the CLI help working.
4. **Followed the human-oversight rules:** when the host lacked `make`, Ruff, pytest and OpenTofu, Codex
   stopped and asked the human to run the networked setup, as `AGENTS.md` requires. It refused to tick M0
   until a clean clone passes CI, instead of declaring success on a Windows-only run.
5. **Exposed a platform risk early:** Codex's environment report showed the Makefile could not run on
   native Windows. That led to two decisions: Linux CI is the acceptance referee, and development moved to
   a Linux toolchain (WSL2) so the commands judges run are the commands that were tested.

### How the repository is built around Codex

The project's working rules live where Codex reads them, so every Codex session starts with them:

| Codex feature | In this repo | What it enforces |
|---|---|---|
| `AGENTS.md` (root, `core/`, `llm/`) | canonical instructions, 14 invariants | trust boundary, no apply path, budgets, honest labels |
| `.codex/config.toml` | workspace-write sandbox, network off, approval on request | nothing Codex runs can reach a cloud account |
| `.codex/rules/*.rules` | command rules | `tofu apply/destroy/state`, `terraform`, `aws`, live demo forbidden |
| Skills (`.agents/skills/`) | `$milestone`, `$check-invariants`, `$add-intervention`, `$score-run`, `$model-bakeoff` | the same procedure for every milestone |
| Reviewer agents (`.codex/agents/`) | `invariant_reviewer`, `methodology_auditor` | independent review with prompts in `docs/review/` |
| Code Review Rules in `AGENTS.md` | P0/P1 rules for `@codex review` | gate overreach, LLM-sourced numbers, missing provenance |
| `scripts/codex-cloud-install.sh` | Codex cloud environment | clean-environment runs of tests and offline mode |

This configuration was drafted with Claude and checked against the Codex documentation; six defects
found in that check are logged under 30 Sep below.

### Optional Codex reviews on build day (only if time allows)

If Codex is available on the work laptop, it reviews Claude Code's milestones read-only with the same
prompts as the Claude Code reviewer subagents, so a second model checks the first. **Delete any row that
is not run before submitting.**

| # | Task | Status | Evidence |
|---|---|---|---|
| R1 | Invariant review of M1–M3 (contracts, factors, ledger, energy) | planned | |
| R2 | Methodology audit of `core/energy.py` and golden tests against METHODOLOGY.md | planned | |
| R3 | Invariant review of M4–M6 (policy, templates, orchestrator, report) | planned | |
| R4 | Invariant review of M6.5 gate (invariant 14: informs, never pushes or merges) | planned | |
| R5 | Judge simulation: read the README cold, list every missing or ambiguous instruction | planned | |

---

## Summary by lifecycle phase

| Phase | Codex | Claude / Claude Code | Human decision |
|---|---|---|---|
| Problem framing | — | candidate solution ideas, form answers | chose "carbon at merge time"; named it EmissionGate |
| Requirements | — | open-source library and licence list | free and open tools only; open-source LLM (organiser rule) |
| Design | works from the design through `AGENTS.md` | architecture, methodology, data contracts, ADRs, PR gate | challenged the missing PR-gate path; approved v1.3 |
| Developer tooling | config, rules, skills, reviewers it runs under | drafted that configuration from Codex docs | approved |
| Implementation | M0 scaffold prototype (work laptop, not in this repo) | all code in this repository | approved each milestone |
| Testing | compile, architecture, capability, literal and secret scans; 32 tests | golden values G1–G7 | ran networked setup |
| Review | cold invariant review of M0; optional reviews R1–R4 | reviewer subagents per milestone; design reviews | decided on each finding |
| Documentation | optional README check (R5) | README, design doc, pitch deck, demo script, this log per milestone | edited and approved |
| Environment | dependencies, OpenTofu, provider mirror on Windows | WSL2 and sandbox setup guidance | moved to Linux toolchain |
| Demo | — | demo script | recorded the video |

---

## Entries

### Sep 2026 — Problem framing — Claude
- **Attempted:** propose solutions for the brief that add measurable sustainability value.
- **Output:** several options; a "carbon at merge time" agent for cloud and AI infrastructure.
- **Decision:** modified. Human chose it, renamed it EmissionGate, and asked for a plain-English
  explanation of each step before going further.
- **Errors found:** none recorded.

### Sep 2026 — Requirements — Claude
- **Attempted:** list every library and model with its licence, under "free and open only".
- **Output:** dependency list; a local open-weight LLM via Ollama.
- **Decision:** modified. Llama (community licence) and Codestral (non-production licence) were
  excluded on licence grounds (ADR-0004).

### Sep 2026 — Design — Claude
- **Attempted:** architecture, agent design, methodology, data contracts, build plan, ADRs.
- **Output:** design document v1.0–v1.2, `docs/` kit, invariants for the coding agent.
- **Decision:** accepted after review.
- **Errors found:** an early GPU saving figure overstated the magnitude. **Corrected:** every figure now
  comes from the Cloud Carbon Footprint coefficients, with golden values in
  [METHODOLOGY.md §6](METHODOLOGY.md) and a "never inflate a per-resource figure" rule.

### 30 Sep 2026 — Developer tooling for Codex — Claude, checked against Codex documentation
- **Attempted:** make the repository Codex-first: `AGENTS.md` as the canonical instructions, `.codex/`
  sandbox and command rules, skills, cold reviewers; keep Claude Code working from the same files.
- **Decision:** accepted.
- **Errors found and corrected while checking the Codex docs:**
  1. `codex review --uncommitted` does not take a custom prompt → the reviewer prompt is piped on
     stdin (`codex review -`).
  2. Skills were hidden from listing → `allow_implicit_invocation: true`.
  3. Custom subagent loading was unreliable → `make codex-review` became the primary review path.
  4. `tofu init` would download providers inside Codex's network-off sandbox and fail → a local
     provider mirror, `tofu init -plugin-dir` everywhere (ADR-0014).
  5. A `GITHUB_TOKEN` in `.env` would be readable by the agent → tokens are exported only in the human's
     terminal (invariant 13).
  6. Two dense Qwen models needed about 24 GB resident → one `gpt-oss-20b` with two reasoning levels
     (ADR-0013), to be confirmed by a measured bake-off.

### 1 Oct 2026 — Design review — human challenge, Claude
- **Human challenge:** "The architecture analyses running resources. Where is the agent that validates
  a PR when infrastructure changes?" The gap was real: the project was named a gate but had none.
- **Output:** gate mode on the same engine — [GATE.md](GATE.md), projection rules for resources with no
  history, golden values G5–G7, ADR-0015, invariant 14 ("the gate informs; humans decide").
- **Decision:** accepted.
- **Weak points declared, not hidden:** utilisation for a new resource is assumed (CCF's 50% default),
  so the gate publishes a 10–90% band; prior art (Carbonifer, Infracost) is acknowledged in GATE.md.

### 1 Oct 2026 — Design review — human question, Claude
- **Human question:** "Is the ledger a file or a database?"
- **Errors found in Claude's own gate design while answering:**
  1. Predictions were keyed to the merge SHA, but the gate runs on `pull_request` and only knows the
     head SHA; squash merges create a new SHA.
  2. No step retrieved predictions for the calibration loop.
  3. Actions artefacts expire after at most 90 days on public repositories.
  4. The design document said verification runs seven days after merge, contradicting the 500-hourly-
     point minimum (about three weeks).
- **Corrected:** `GatePrediction` keyed by PR and head SHA, read-only retrieval in `sync-feedback`,
  `retention-days: 90`, limitation documented, timing fixed (kit v3.1).

### 4–5 Oct 2026 — Implementation, M0 scaffold — Codex (work laptop, Windows)
- **Attempted:** `$milestone M0` — package layout, CLI with stub commands, architecture test.
- **Output:** scaffold plus Codex's own checks: Python compilation, core-import architecture scan,
  agent-file consistency, dangerous-capability scan, literal-coefficient scan, secret scan, and a cold
  invariant review with no violations.
- **Error found by Codex:** the host had no `make`, Ruff, pytest or OpenTofu. Codex stopped and asked
  the human to run the networked setup, as the project rules require. Next day it installed the
  dependencies and OpenTofu, built the provider mirror, fixed formatting, and reported 32 passing tests.
  It kept M0 unticked until a clean clone passes CI.
- **Decision:** modified.
- **Errors found in human review (with Claude):**
  1. The repository lived in a synced OneDrive folder with spaces in the path — breaks `make`, and sync
     locks can corrupt git and SQLite files.
  2. The Makefile had never run: Codex used PowerShell equivalents, so results were Windows-only while
     CI and judges use Linux.
  3. Codex performed networked installs, although the design keeps the coding agent offline.
  4. ADR-0013 claimed `gpt-oss-20b` fits 16 GB machines; OpenAI's guidance is ≥ 16 GB of GPU or unified
     memory, so it does not fit a 16 GB-RAM laptop without a GPU.
- **Corrective steps:** development moved to a 32 GB personal machine under WSL2 with the coding agent
  sandboxed; Linux CI is the acceptance referee; networked steps are run by the human only.
- **Outcome:** the prototype was not carried into this repository; the submission was rebuilt from scratch
  with Claude Code (ADR-0016).

---

## Build day — 5 Oct 2026

The coding agent appends one entry per milestone, in this format, before asking the human to approve
the milestone. Entries are factual: what failed is recorded, not smoothed over.

```markdown
### <date> <time> — M<n> <name> — <tool>
- **Attempted:** <what was asked>
- **Output:** <files, tests, commands that now work>
- **Decision:** accepted | modified | rejected — <by the human, and why>
- **Errors found:** <failing tests, wrong assumptions, review findings — and who found them>
- **Corrective steps:** <what changed>
- **Evidence:** <commit SHA, test names, command output summary>
```

<!-- build-day entries go below this line -->

### 5 Oct 2026 13:40 IST — M0 Scaffold — Claude Code
- **Attempted:** environment bring-up and `/milestone M0`: package layout, typer CLI with stub commands,
  architecture test.
- **Output:** `src/emissiongate/` with `cli`, `orchestrator`, `agents`, `core` (+`patches`), `llm`, `tools`,
  `report`; `tests/unit/test_architecture.py` (core may import only stdlib, pydantic, yaml, contracts and
  core; no subprocess/socket/urllib/http; llm and tools never import agents/orchestrator; no boto3 and no
  apply/destroy/import/state command lists anywhere); `tests/unit/test_cli.py`.
- **Decision:** accepted by the human, with environment changes: the human approved installing OpenTofu
  1.13 and Ollama via winget, Python deps via uv, and the signed AWS provider mirror; chose to move the
  repo out of OneDrive to `C:\dev\emissiongate`.
- **Errors found:** (1) the planned WSL2 environment did not exist on the machine — found by Claude Code
  when probing tools (no WSL, no `make`, no `tofu`); (2) the given `scripts/check_agent_files.py` fails the
  repo's own `ruff` line-length rule — found by Claude Code on the first `ruff check`; (3) a probe command
  that included `terraform version` was blocked by `.claude/settings.json` (deny rule worked as designed).
- **Corrective steps:** ADR-0017 records native Windows + Linux CI as referee; a per-file `E501` ignore for
  the given script (content unchanged apart from `ruff format`); `score --latest` accepted by the stub so
  `make demo-offline score` in CI exits 0.
- **Evidence:** `ruff check` and `ruff format --check` clean; `pytest` 7 passed; `python -m emissiongate
  --help` lists estate, run, gate, score, sync-feedback, grid-snapshot, report; `agent-check` consistent.

### 5 Oct 2026 14:20 IST — M1 Contracts, factors, ledger — Claude Code
- **Attempted:** `/milestone M1`: `contracts.py` from DATA_CONTRACTS, factor loader with provenance,
  append-only SQLite ledger.
- **Output:** `contracts.py` (copied verbatim by script from the doc's code block; five optional
  `Utilisation` fields added to both doc and code for schedule savings and the month-end trap);
  `core/factors.py` (`instance`, `processor_watts` averaged, `region_g_per_kwh` tier `annual`, constants,
  replication; `FactorNotFound` for unknown types, processors, regions and the `unknown` pseudo-region);
  `core/ledger.py` (INSERT-only, triggers reject UPDATE/DELETE, monotonic `seq`, payloads stored by
  SHA-256, scalar-only `detail`, injected clock, `LedgerWriteError` on failure).
- **Decision:** accepted (human approval requested with the commit).
- **Errors found:** the verbatim contracts contain `×` in a comment, which `ruff` RUF003 rejects — found
  by `ruff check`. Methodology audit (separate subagent, below) found a latent hidden default
  `raw.get("gpu_count", 0)` (P0 under core rules).
- **Corrective steps:** `allowed-confusables` for `× − –` in `pyproject.toml` (keeps the copy verbatim);
  `gpu_count` now required, missing → `FactorNotFound`.
- **Evidence:** `tests/unit/test_factors.py` (all 7 estate instance types, unknown type/region raise),
  `tests/unit/test_ledger.py` (UPDATE/DELETE rejected, closed DB write raises), `test_contracts.py`
  (frozen, extra forbidden, LLM-facing models have no numeric fields).

### 5 Oct 2026 14:45 IST — M3 Energy and emissions — Claude Code; review by methodology-auditor subagent
- **Attempted:** `/milestone M3`, tests first: golden G1–G4, then `core/energy.py` and `core/grid.py`.
- **Output:** `compute()` (per-vCPU and per-GPU watts, EG-simplification-1 memory, PUE),
  `storage()` (SSD/HDD × replication × PUE), `kg_co2e`, `emission_record()` merging coefficient and grid
  provenance; `core/grid.py` annual tier plus a strict snapshot parser for later time-shifting.
- **Decision:** accepted (human approval requested with the commit).
- **Errors found:** (1) two golden savings failed by 0.0006 — found by the tests. The doc's savings are
  differences of the rounded before/after values (138.794 − 42.170 = 96.624), while the unrounded
  difference is 96.6246. Code was right; the doc was ambiguous. (2) The methodology-auditor subagent
  (cold review, read-only, recomputed G1–G7 from the raw factors file) found no formula drift, confirmed
  reading (1) is fair (not a hidden change), and raised P1: emissions dropped the `annual`-tier
  provenance; P2: `u_gpu` defaulted to 0 for GPU instances; snapshot slots not converted to UTC; loose
  test tolerance; storage-class → medium mapping is hand-typed (declared, not vendored).
- **Corrective steps:** METHODOLOGY §6 clarification paragraph (no formula changed; G2, G3, G6 named);
  tests assert both the rounded-difference golden and the unrounded value at 3 dp; `emission_record()`
  plus a test that provenance tiers are `{vendored, annual}`; `u_gpu` required for GPU instances; snapshot
  parser converts to UTC, keeps the last 7 days, checks region and full slot coverage. Not fixed (P2,
  recorded): storage-class mapping stays in code with a CCF citation; network kWh unused in v1.
- **Evidence:** `tests/golden/test_golden_energy.py` — G1–G4 at 3 dp; `pytest` 48 passed.

---

## Totals (fill in at submission)

| | Count |
|---|---|
| Milestones attempted / accepted | — |
| Codex reviews run / findings / findings fixed | — / — / — |
| AI outputs accepted as-is / modified / rejected | — / — / — |
| Errors found by AI self-check / by cross-tool review / by tests / by human review | — / — / — / — |
