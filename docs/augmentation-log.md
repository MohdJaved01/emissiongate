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
- Networked steps (installs, provider mirror, model pull, the grid snapshot) and every commit and push
  ran only after the human's explicit approval in the session; on build day Claude Code ran them once
  approved (ADR-0017).
- A human approves each milestone before it is ticked in [BUILD_PLAN.md](BUILD_PLAN.md).
- Reviewer subagents in separate, read-only contexts checked M3 (methodology), M6 and M6.5
  (invariants), as BUILD_PLAN requires, and read the README as a judge before submission.

---

## Codex across the lifecycle

**Why Codex's role is limited.** Codex licences were provided late in the hackathon window
(on 1 Oct 2026). Codex built and checked an M0 scaffold on a Windows work laptop on
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
   a Linux toolchain (WSL2) so the commands judges run are the commands that were tested. (On build day
   WSL2 was not available; ADR-0017 records the native-Windows build with Linux CI as the referee.)

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

### Codex reviews on build day

None were run on build day; Codex was not used. Independent review of Claude Code's milestones
was done by Claude Code reviewer subagents in separate, read-only contexts driven by the same prompts
(`docs/review/methodology-auditor.md`, `docs/review/invariant-reviewer.md`): one methodology audit
after M3, invariant reviews after M6 and M6.5, and a judge-style README read before submission. A
second model (Codex) would be a stronger cross-check; that is listed as not done.

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
| Review | cold invariant review of M0 (prototype) | reviewer subagents after M3, M6, M6.5; judge-style README read; design reviews | decided on each finding |
| Documentation | — | README, design doc, pitch deck, demo script, this log per milestone | edited and approved |
| Environment | dependencies, OpenTofu, provider mirror on Windows | native-Windows bring-up on build day (ADR-0017) | moved the repo out of OneDrive; approved each install |
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

### 5 Oct 2026 13:38 IST — M0 Scaffold — Claude Code
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

### 5 Oct 2026 13:48 IST — M1 Contracts, factors, ledger — Claude Code
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

### 5 Oct 2026 13:48 IST — M3 Energy and emissions — Claude Code; review by methodology-auditor subagent
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

### 5 Oct 2026 13:58 IST — M2 Synthetic estate generator — Claude Code
- **Attempted:** `/milestone M2`: seeded generator for CUR, metrics, prices, CCFT totals, ground truth,
  manifest and the Terraform estate; offline `tofu validate`.
- **Output:** `src/emissiongate/estate/` (generator in the package so the estate repo's CI can run
  `emissiongate estate --telemetry-only` after install; `scripts/generate_estate.py` is a thin wrapper);
  `core/hcl.py` writes `tofu fmt`-clean HCL and edits one attribute inside one named block;
  `tools/tf.py` (plan-only: `init -plugin-dir`, `fmt -check`, `validate`, `plan -refresh=false`,
  `show -json`; any other subcommand raises; `AWS_*` env vars stripped).
- **Decision:** accepted (human approval requested with the commit). `--inject corrupt-cur` cut per plan.
- **Errors found:** (1) by Claude Code's timing check: the first `tofu validate` in each fresh workspace
  took 44–49 s on Windows (first run of a newly copied 800 MB provider binary) against 3 s afterwards;
  (2) the doc's tag list for `compliance-logs` would have refused it on a missing `Environment` tag before
  the regulatory rule was ever exercised — judged a test-design gap, not a trap change.
- **Corrective steps:** shared `TF_DATA_DIR` (`.eg-cache/tofu-data`, gitignored): the provider is installed
  from the mirror once per machine, next workspaces validate in ~3 s. `Environment=prod` added to
  `compliance-logs`, recorded in SYNTHETIC_ESTATE.
- **Evidence:** `tests/unit/test_generator.py`: same seed → identical SHA-256 manifest; 10 ground-truth
  entries, 3 traps; versions.tf copied; every output labelled synthetic; exact pattern means;
  `@tofu` test: init from the mirror + fmt + validate + plan pass offline. `pytest` 55 passed.

### 5 Oct 2026 14:10 IST — M4 Collector, policy, ranking — Claude Code
- **Attempted:** `/milestone M4`: DuckDB CUR reader, metrics reader, collector, fail-closed policy,
  savings per template, carbon and cost ranks.
- **Output:** `tools/cur.py`, `tools/metrics.py`, `agents/collector.py`, `agents/quantifier.py`,
  `agents/strategist.py`; `core/utilisation.py` (35-day window, `min_datapoints`, hour-of-week mask,
  weekly regularity, mask coverage, off-mask load), `core/policy.py` (refuse → missing tag → restrict →
  suppressions; malformed policy raises `PolicyError`), `core/interventions.py` (eligibility, allowed
  values, defaults, savings recomputed from chosen params), `core/ranking.py`. New threshold
  `schedule_min_mask_coverage: 0.95` in `policy.yaml`.
- **Decision:** accepted (human approval requested with the commit).
- **Errors found (by Claude Code, from the first sweep output):** (1) S3 size used binary TB (×1024) while
  EBS and METHODOLOGY G4 use decimal TB — 40 TB showed 1588 kWh instead of 1551.046; (2) a garbled
  `count` expression in the collector; (3) a guardrail check that detected refusals by string suffix —
  fragile for a fail-closed rule; (4) without a coverage check, `monthend-close` (idle in 4 of 5 weeks)
  scored 0.8 weekly regularity, enough to pass as "weekly".
- **Error found in this log (by Claude Code, checking the clock):** the M1, M3 and M2 entries had
  been stamped with estimated times (14:20–15:30) that were later than the real commits. Corrected to
  the commit times from `git log` (13:48, 13:48, 13:58).
- **Corrective steps:** decimal TB everywhere; explicit refusal/restriction lists; `mask_coverage`
  threshold (monthend coverage = 0.0, dev-api = 1.0); schedule also blocked by `Environment=prod`.
- **Evidence:** seed 42: carbon order gpu-inference (−258.1), legacy-worker (−218.6), reporting-db
  (−96.6), dev-api (−34.8); cost order gpu, reporting-db, dev-api, legacy-worker; dr-standby blocked by
  `tag:Role=DR` + `missing-tag:Owner`; monthend-close no candidate (p95 0.92, coverage 0); compliance-logs
  storage_tier only, ≈0 kg, 9.1k USD synthetic, `expiration` forbidden; orphaned-ebs decommission
  advisory. `tests/unit/test_strategy_m4.py`, `tests/unit/test_policy.py`.

### 5 Oct 2026 14:10 IST — M5 Patch templates and validation — Claude Code
- **Attempted:** `/milestone M5`: five templates, registry, renderer returning full file contents, plan
  validation, `--inject bad-param`.
- **Output:** `core/patches/{rightsize,schedule,graviton,storage_tier,time_shift}.py`; registry and
  `validate_params` (keys ⊆ options, values ∈ allowed); renderer refuses `expiration`, `force_destroy`,
  `prevent_destroy` and no-op renders; edits only the candidate's own file.
- **Decision:** accepted (human approval requested with the commit).
- **Errors found:** `tofu fmt` writes empty blocks as `filter {}` — the HCL writer would have emitted a
  two-line empty block (caught while writing `storage_tier`, before the test run).
- **Corrective steps:** empty blocks render as `name {}`.
- **Evidence:** `tests/unit/test_patches.py`: every template's diff touches one file and at most two
  existing lines; all six cases pass `fmt -check`, `validate`, `plan -refresh=false` offline in one
  shared workspace; the injected bad image variable fails with a ≤4 KB stderr tail naming it.

### 5 Oct 2026 14:30 IST — M6 Orchestrator and offline mode end to end (+ M10 CodeCarbon, M11 score) — Claude Code; review by invariant-reviewer subagent
- **Attempted:** `/milestone M6`: run- and candidate-level state machine, checkpoints, budget ceilings,
  validator with bounded repair, PR body template, HTML run report, `score`, CodeCarbon block.
- **Output:** `orchestrator/{machine,budget,checkpoint,measure}.py`, `agents/{validator,decider}.py`,
  `core/{sci,scoring,claims}.py`, `report/render.py` + `templates/{pr_body.md.j2,report.html.j2}`, CLI
  `run` (Gate 1 prompt unless `--approve`, records the approver) and `score`.
- **Decision:** accepted (human approval requested with the commit). `--resume` not built (BUILD_PLAN
  "if behind: skip --resume"); `checkpoint.json` is written before every transition.
- **Errors found:** (1) Windows console (cp1252) crashed on the `−` sign — found on the first run;
  (2) rich swallowed `[tag:Role=DR, …]` as markup, hiding guardrail reasons — found by reading the output;
  (3) ranking table rounded savings directly (34.8) while the PR title published the difference of rounded
  values (−34.7) — found by reading the output; (4) CodeCarbon on this laptop measures CPU via Windows EMI
  counters but **models RAM at a fixed 20 W** — ~80% of the total in a 4-second probe, 45–62% in full runs — labelling the run "measured" would have
  overstated it. (5) Invariant-reviewer subagent (cold, read-only): no P0; **P1** published PR figures
  (from re-valuation) had no ledger event and time-shift rows would mislabel their grid tier (inv. 4);
  **P1** LLM narrative/risks would reach the PR body without the numeric-claim scan (inv. 1); **P1** a
  missing synthetic price became a silent zero cost change (core hidden-default rule); **P2** LLM ceilings
  could never stop the run (inv. 9); three tool calls unledgered (inv. 8); gate diff collector defaulted
  unknown plan attributes (inv. 5); acceptance reason could predate the label or come from a bot (inv. 14).
- **Corrective steps:** UTF-8 stdout; markup escaped; one published-delta rule everywhere; energy label
  `estimated` unless every non-zero component is hardware-measured, with the measured CPU share stated;
  ledger event per valuation (strategist) and per published valuation (validator), cited in the PR body,
  tier shown per ranking row; `core/claims.py` scan on narrative and risks → template fallback + `fallback`
  event; missing price raises → "not quantified"; `>=` ceilings; ledger for `tofu version`, metrics miss,
  `tofu init` failure; unknown plan attributes → not quantified with reason; acceptance requires a `User`
  comment posted after the `labeled` event.
- **Evidence:** `make demo-offline` equivalent on Windows (first offline run `20261005T084721Z-offline-s42`):
  44 s, `DONE`, 4 PR drafts, all plans pass first attempt, coverage 100%, LLM calls 0; agent energy
  0.000345 kWh (estimated), 0.25 gCO2e/run. The README quotes the later run `20261005T090230Z-offline-s42`
  (with the grid snapshot): 0.000360 kWh, 0.26 g.
  `score`: precision 1.00, recall 0.80 (FN: nightly-etl time_shift — no grid snapshot), 0 trap violations.
  `tests/ground_truth/test_offline_pipeline.py` (thresholds, ledgered transitions, PR numbers from core,
  `--inject bad-param` repaired on attempt 2), `tests/unit/test_claims.py`.

### 5 Oct 2026 14:31 IST — M9 (part) UK grid snapshot — Claude Code, network step approved by the human
- **Attempted:** recall was 0.80 because `time_shift` had no grid data; the human approved fetching one
  snapshot from the public UK Carbon Intensity API (no key, CC BY 4.0) and committing it.
- **Output:** `tools/grid_uk.py` (httpx, 5 s timeout, 2 retries; London region id looked up via
  `/regional`, found 13), `emissiongate grid-snapshot`, `fixtures/grid/uk_london_2026-10-05.json`
  (336 history + 97 forecast half-hour slots, labelled `synthetic: false`, with attribution).
- **Decision:** accepted (human approved the fetch).
- **Errors found:** the day parser crashed on the daily recurrence `0 2 * * *` (`*` days) — found on the
  first run with the snapshot.
- **Corrective steps:** `*` handled. Result reported as it is: moving the 2-hour batch inside 00:00–06:00
  saves **0.035 kgCO2e/yr** on this week's London grid, below `min_saving_kg_co2e_yr` (5), so it is an
  advisory, not a PR. Recall stays 0.80; the threshold was not tuned.
- **Evidence:** ledger event for `nightly-etl:time_shift` with tiers `snapshot,vendored`.

### 5 Oct 2026 15:58 IST — M6.5 PR gate — Claude Code; review by invariant-reviewer subagent
- **Attempted:** `/milestone M6.5`: diff collector over `tofu show -json` of base and head, projections
  (METHODOLOGY §3b, G5–G7), suggestions from the sweep's templates validated with `tofu plan`, sticky
  comment, acknowledgement label, prediction record, the estate repo's workflow.
- **Output:** `orchestrator/gate.py`, `agents/{diff_collector,reporter}.py`, `core/{projection,safety}.py`,
  `tools/{github,gitrefs}.py`, `report/templates/gate_comment.md.j2`, CLI `gate`; `estate-repo/`
  (workflow, README, .gitignore) and `scripts/build_estate_repo.py`. The workflow the docs called
  "given" was not in the kit; it was written today.
- **Decision:** accepted (human approval requested with the commit).
- **Errors found:** (1) by Claude Code: `agents/reporter.py` imported from `orchestrator/` (wrong import
  direction); the not-evaluated message repeated itself and dumped the whole `tofu init` output.
  (2) Invariant-reviewer subagent, no P0, **8 P1**: the documented "comment, then label" order was
  rejected by the code; an acknowledgement carried over to later pushes; GitHub errors (fork 403) and an
  unparseable cron day could fail the check outside the thresholds; the "before" side and suggestions
  of assumed resources were not published as ranges; the comment cited no ledger event ids and
  suggestions were unledgered; several tofu/git/metrics/GitHub calls and the plan-failure stderr were
  unledgered; **untrusted PR HCL was planned with `GITHUB_TOKEN` in tofu's environment and with backend
  init enabled** (a data source with custom endpoints plus `file("/proc/self/environ")` could have
  exfiltrated it); the gate ignored `policy.yaml → ceilings`. P2: storage rows labelled "observed",
  hard-coded window length, unknown schedule capacity defaulted to 0, assumed schedule hard-coded.
- **Corrective steps:** acknowledgement = latest `User` label event plus a `User` reason comment, either
  order, both newer than the head commit (re-acknowledge after a push); GitHub errors ledgered as
  `fallback`, exit code follows status only; numeric cron days parsed, unknown recurrences → not
  quantified; `Projection` and `GateSuggestion` carry the assumption band on both sides
  (DATA_CONTRACTS updated first); projection and suggestion ledger ids in the comment; every tool call
  ledgered; tofu env strips tokens/secrets, `init -backend=false`, `core/safety.py` refuses data sources,
  non-local modules, custom endpoints, remote backends, non-AWS providers and absolute-path file reads
  before any plan; workflow checkouts use `persist-credentials: false`; `Budget(policy.ceilings)` checked
  before each plan; assumed schedule moved to `policy.yaml → gate.assumed_schedule`.
- **Evidence:** G5–G7 to 3 decimals (`tests/golden/test_golden_gate.py`); `tests/ground_truth/
  test_gate_scenarios.py`: 2 × g5.2xlarge → `ack_required`, +683.5 (263.1–1,103.9) with a validated,
  ledgered schedule suggestion (assumed range); legacy-worker 6→10 → `pass_with_warning` +59.2 with
  Graviton −232.2; tags-only → no comment; invalid HCL → `not_evaluated`, exit 0; data source → not
  planned. `tests/unit/test_gate_github.py` (respx): bot label refused, reason before/after label,
  no carry-over after a push, sticky comment PATCH/POST. `tests/unit/test_safety.py`. `pytest` 148 passed.

### 5 Oct 2026 15:58 IST — M7 Local LLM layer (minimal) — Claude Code
- **Attempted:** `/milestone M7` minimal scope (BUILD_PLAN today): the LLM chooses template parameters and
  writes the PR narrative; schema re-ask, then rule fallback; repair from plan stderr.
- **Output:** `llm/{client,ollama,factory,calls}.py`, prompts `system.j2`, `decide_patch.j2`,
  `repair_params.j2`, `narrative.j2`. Non-streaming `/api/chat`, `format` = pydantic schema, `think` per
  tier from `EG_THINK_*`, `num_ctx` and temperature explicit (0 for decisions, 0.3 for prose), fence
  stripping, one re-ask, `None` → deterministic path; `message.thinking` stored only as a SHA-256.
  Every call ledgered with `model@think`, prompt/completion tokens and duration; budget charged.
  Not built: scan planning and ambiguous classification call sites.
- **Decision:** accepted (human approval requested with the commit). The human approved installing
  Ollama and pulling `gpt-oss:20b` at 13:20.
- **Errors found:** none in the LLM path during the run; the numeric-claim guard and parameter validation
  came from the M6 invariant review.
- **Evidence:** real run `20261005T091433Z-local-s42` on this laptop (CPU inference): 8 LLM calls, 8/8
  schema-valid first try, 0 fallbacks, 6,624 tokens, 14–123 s per call; all 4 decisions by the model,
  within allowed values (it chose the rule defaults); narratives contain no numbers; every plan passed
  first attempt. Agent energy 0.005228 kWh (estimated) vs 0.000345 kWh offline → marginal LLM energy
  ≈ 0.0049 kWh per run. `tests/unit/test_llm.py` (fake transport): fenced JSON, re-ask, double failure,
  connection error, disallowed values → rule, numeric-claim narrative → template, ledger has tokens and
  no thinking text.

### 5 Oct 2026 16:09 IST — Live gate PR, results and judge-style README review — Claude Code; review by a reviewer subagent
- **Attempted:** open the gate demo PR on the estate repo (human-approved), fill the README results from
  real runs, then have a fresh subagent read the README cold as a judge and check it against the repo.
- **Output:** [emissiongate-demo-estate PR #1](https://github.com/MohdJaved01/emissiongate-demo-estate/pull/1):
  the workflow posted the sticky comment (❌ acknowledgement required, +683.5 kgCO2e/yr, 263.1–1,103.9
  assumed, schedule suggestion −439.4 validated) and failed the check as designed; CI green on Ubuntu for
  every push. `docs/sample-run/` (the local run's report, PR drafts and manifest, synthetic).
- **Decision:** the acknowledgement label is left to the human (invariant 14); Claude Code does not add it.
- **Errors found by the judge-review subagent:** README sweep table showed 3 of the 4 PRs, so 608.1 did not
  add up on the page; energy figures differed between README and this log (two different runs, unnamed);
  a g/kg unit slip; "only networked step", "G1–G7 in M3", "laptop without power counters", "low reasoning
  by default" and "LLM test cases" were inaccurate; the intended red ❌ on PR #1 was unexplained; no sample
  output without installing; this log kept orphan R1–R5 rows (left by an earlier edit of mine), a stale
  "every milestone reviewed" rule and a WSL2 statement contradicting ADR-0017; AGENT_DESIGN listed unbuilt
  LLM call sites and "measured energy"; the pitch deck (slide 7) says "573 kgCO2e/yr avoided".
- **Corrective steps:** all README, log and AGENT_DESIGN items fixed. **Not fixed: the pitch deck** — the
  .pptx/.pdf need the human to edit slide 7 to "608 kgCO2e/yr proposed (not merged) · +684 flagged at
  review" and re-export.
- **Evidence:** this commit; `gh pr view 1 --repo MohdJaved01/emissiongate-demo-estate --comments`.

---

## After build day

### 6 Oct 2026 16:24 IST — Submission check against the hackathon brief — Claude Code
- **Attempted:** the human pasted the five repository requirements (README, agent design document, pitch
  deck, demo video, this log) and allowed Claude Code to update anything that fell short. Claude Code
  checked each deliverable against the brief and the code.
- **Output:** README and this log already met the brief. Pitch deck: edited in PowerPoint through COM
  automation driven by Claude Code, PDF re-exported from PowerPoint, every changed slide rendered and
  inspected. AGENT_DESIGN: statements aligned with what is built.
- **Decision:** the human allowed the update; the commit waits for the human's approval.
- **Errors found (by Claude Code, comparing the documents with the code):**
  - **Pitch deck:**
    1. Slide 7 said "573 kgCO2e/yr avoided by three sweep fixes", and its chart had three of the four
       PRs.
    2. Slide 7 said "+684 stopped at review", but the gate flags the change; a human decides.
    3. Slide 4 coloured the Planner as an LLM step, but LLM scan planning is not built.
    4. Slide 9 said "low reasoning by default" and "estimated where the laptop has no power counters".
       The judge review had already corrected both in the README.
    5. The speaker notes on slide 7 listed three fixes. The notes on slide 5 said rejection labels
       "become rules", which is not built.
  - **AGENT_DESIGN** described designed-only parts as working:
    1. a Planner agent that calls the LLM
    2. resumable runs
    3. a live grid API with fallback at run time
    4. opening PRs in live mode
    5. rejection labels turned into suppressions
    6. skipping a malformed billing partition
    7. power counters (same issue as slide 9)

    The detailed diagrams show the full design without saying which parts are unbuilt.
  - **Claude Code's own errors:**
    1. The first recolour of slide 4 filled the Planner's text box instead of its rectangle, and the box
       rendered white. Claude Code found it by viewing the rendered slide.
    2. Claude Code wrongly flagged the "Ollama not running → whole run continues offline" row as an
       overclaim and rewrote it as per-call fallback. It found the error itself in the next entry while
       reading `llm/factory.py`: an unreachable Ollama at start does switch the whole run to offline
       behaviour, and the report says so. The row now describes both cases.
- **Corrective steps:**
  - **Slide 7:**
    - The figure is now "608 kgCO2e/yr in four sweep fix PRs: proposed, not merged".
    - The dev API bar (−34.7) is added to the chart.
    - The gate figure is now "+684 flagged at review (range 263–1,104, assumed load)".
    - The footnote now carries the run metrics: precision, recall, trap violations and the agent's
      grams per run.
  - **Slide 4:** the Planner is shown as deterministic code ("scope · budget ceilings").
  - **Slide 9:** the wording now matches the README.
  - **Speaker notes:** corrected on slides 5 and 7.
  - **AGENT_DESIGN:** a built-vs-designed note sits under the diagrams, and each overstated row now
    says what runs today.
  - **Slide 4 recolour:** fixed by recolouring the rectangle and matching its border.
- **Evidence:** this commit. Slide text was extracted from the .pptx after the edit, and the PDF has 10
  pages (PowerPoint export).

### 6 Oct 2026 16:30 IST — Gate walkthrough and adoption guide — Claude Code, from a page the human shared
- **Attempted:** the human shared a claude.ai explainer page on how the PR gate runs and how another
  repository could use it, and asked for it to be added to a document or slide. Claude Code checked
  every claim on the page against the workflow, the code and PR #1 (`gh pr view`, `gh run list`,
  read-only) before adding it.
- **Output:**
  - `docs/USING_THE_GATE.md`: PR #1 step by step, how the check is decided, how a red check turns green,
    and what another repository needs.
  - Links to it from the README and AGENT_DESIGN.
  - Slide 3 says a repository opts in by adding one workflow file. Slide 10's "Next" adds "Gate on real
    repos". A speaker note on slide 3 points to the document.
  - The deck stays at 10 slides, the brief's maximum.
- **Decision:** the human asked for the addition; the commit waits for the human's approval.
- **Errors found in the shared page (by Claude Code, against the code):**
  1. The token count was 6,623; the manifest says 6,624.
  2. It said the gate repairs a failing suggestion up to 3 times; the gate drops it.
  3. It listed S3 lifecycle rules among the resources the gate quantifies; they are not.
  4. It called the hosted-LLM switch an optional feature; `llm/factory.py` treats it as not enabled.
  5. Under "works today" it left out the safety screen. Data sources, registry or git modules and remote
     backends make a PR "not evaluated".
  6. It also left out that plans run with no credentials. A real provider block will not plan without
     the estate's dummy keys.
  7. It left out the AWS provider pin (`~> 6.0`).
- **Corrective steps:**
  - The document uses the code's behaviour for each of these.
  - It adds the safety screen as an explicit step.
  - It lists the real-repository gaps under "Needs work".
  - AGENT_DESIGN's built-vs-designed note now also lists suggestion repair in the gate.
- **Evidence:** this commit. PR #1 job 69 s (10:31:53–10:33:02 UTC), check 25.8 s and 0.383 Wh, both
  from the posted comment.

### 6 Oct 2026 16:57 IST — Built-vs-designed marks on the diagrams and spec docs — Claude Code
- **Attempted:**
  - The human asked whether the architecture diagrams needed revisiting.
  - Claude Code recommended marking their designed-only parts.
  - The human agreed.
- **Output:**
  - **Diagrams:** the three diagrams in `docs/img/` now carry a dark "designed" tag on each
    designed-only element, plus a key entry: 7 tags on the sweep diagram, 4 on the gate diagram, 2 on
    the overview.
    - **How they were made:** the original PNGs were placed in PowerPoint through COM, the tags were
      overlaid, and each image was exported at its original pixel size (3212 × 1720 and 3212 × 896).
    - **What did not change:** the rest of each image.
  - **Spec docs:** ARCHITECTURE.md and GATE.md now open with a pointer to the README status table.
- **Decision:** the human approved the change and the commit.
- **Errors found (by Claude Code, viewing each render):**
  - On the sweep diagram, the first "live PRs" tag clipped the text below it.
  - The overview's tags and legend were too small for that image's larger text.
- **Corrective steps:**
  - The "live PRs" tag was moved up.
  - The overview's tags were enlarged.
  - The key text now uses the key's own font and size.
- **Not changed:** the copy of the overview inside slide 3. Tags at that size would be unreadable, and
  slide 10's roadmap lists the same items.
- **Evidence:** this commit.

---

## Totals (fill in at submission)

| | Count |
|---|---|
| Milestones attempted / accepted (build day) | 10 / 10 — M0, M1, M2, M3, M4, M5, M6 (+M10/M11 parts), M6.5, M7 (minimal), M9 (part) |
| Codex reviews run / findings / findings fixed | 0 / 0 / 0 (not run on build day) |
| Reviewer-subagent reviews run / findings / findings fixed | 4 / 26 code findings (1 P0, 12 P1, 13 P2) + 17 README/doc findings / 23 code (every P0 and P1; 10 of 13 P2) + 16 doc (deck left to the human) |
| AI outputs accepted as-is / modified / rejected (human decision per commit) | 10 / 0 / 0 — the human approved every milestone commit; Claude Code modified its own output after reviews before asking |
| Errors found by AI self-check / by reviewer subagents / by tests / by human review | 18 / 26 / 1 / 0 on build day (earlier human-review findings are in the 4–5 Oct entry) |

P2 findings left open, recorded: the storage-class → SSD/HDD mapping is hand-typed in `core/energy.py`
(with a CCF citation) rather than vendored; network energy is not modelled; the gate's suggestion
selection lives in `orchestrator/gate.py` rather than `core/`.
