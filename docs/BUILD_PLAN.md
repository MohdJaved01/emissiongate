# Build plan

Work top to bottom. Each milestone ends in a green `make lint test` and its acceptance criteria.
Use `$milestone M<n>` in Codex or `/milestone M<n>` in Claude Code. Tick the box in this file in the
same commit that completes it.

## Submission scope — 5 Oct 2026 (overrides the order below for today)

Submission is due today with a 3–5 minute video of the agent running. Working code beats coverage.

| Order | Work | Target | If behind |
|---|---|---|---|
| 1 | M0 scaffold (rebuild on Linux; `make setup lint test` must pass) | 13:00 | — |
| 2 | M1 contracts, factors, ledger | 13:45 | — |
| 3 | M2 synthetic estate | 14:45 | drop `--inject corrupt-cur` |
| 4 | M3 energy, golden G1–G4 | 15:15 | — |
| 5 | M4 collector, policy, ranking | 16:00 | — |
| 6 | M5 templates + `tofu plan` validation | 16:45 | build `schedule`, `graviton`, `rightsize` first; the other two can follow |
| 7 | M6 offline end to end, plus a minimal `emissiongate score` (M11) and the CodeCarbon block of M10 | 17:30 | skip `--resume` |
| 8 | M6.5 gate: CLI, comment, workflow, the demo PR | 18:45 | suggestions without the repair loop |
| 9 | M7 minimal: LLM chooses template parameters and writes the PR narrative; schema re-ask then rule fallback | 19:30 | narrative only |
| — | **Feature freeze 19:30.** Record the video. | | |
| 10 | Fill README results and status tables from real runs; final augmentation-log totals | 21:00 | — |

Gate demo branch: in `emissiongate-demo-estate`, branch `demo/add-gpu-fleet` adds one file with an
`aws_autoscaling_group` of 2 × `g5.2xlarge` in us-east-1, no schedule. Open it as a PR and leave it open
with the comment showing (expected: +683.5 kgCO2e/yr, range 263.1–1,103.9, acknowledgement required).

Cut for today, kept as "designed, not built" in the README: M1.5 bake-off, M8 live PRs and feedback
sync, M9 live grid API, calibration loop, `make compare`.

After **every** milestone: run `make lint test`, append an entry to `docs/augmentation-log.md`, commit,
and ask the human to approve before ticking the box.

Review: after M3, M6 and M6.5 run the invariant-reviewer subagent (`.claude/agents/`, same prompt as
`docs/review/invariant-reviewer.md`), and the methodology auditor after M3. If Codex is available on the
work laptop, it may run the same prompts read-only. Fix P0/P1 findings before moving on and log each
review. Before submitting, have a fresh reviewer read the README as a judge would and list any gaps.

---

The critical path for a submittable demo is **M0 → M6 → M6.5** (offline sweep end to end, then the PR
gate — the literal "carbon at merge time" step). M1.5 (model bake-off)
runs in parallel and should finish early — it decides the runtime model. M7–M11 add the LLM, live PRs,
live grid data, the footprint numbers and polish. If time runs short, ship M0–M6.5 plus M10.

---

## M0 — Scaffold  `[ ]`

- `pyproject.toml` (given), `src/emissiongate/` package with the directories in CLAUDE.md, empty
  `__init__.py` files, `cli.py` with a typer app and stub commands that exit 0.
- `tests/unit/test_architecture.py`: fails if any module under `emissiongate.core` imports
  `emissiongate.llm`, `emissiongate.tools`, `httpx`, `subprocess`, `socket` or `urllib.request`.
- `.github/workflows/ci.yml` (given) green, including `make agent-check` and `make providers`.
- Nested `AGENTS.md` files in `core/` and `llm/` (given) stay in place; don't delete them when scaffolding.

**Done when:** `make setup lint test` passes on a clean clone; `python -m emissiongate --help` lists
`estate run score sync-feedback grid-snapshot report`.

## M1 — Contracts, factors, ledger  `[ ]`

- `contracts.py` copied from `docs/DATA_CONTRACTS.md`.
- `core/factors.py`: load `factors/ccf_aws_f584c54.json`; expose `processor_watts(names)` (averaged),
  `instance(type)`, `region_g_per_kwh(region)`, constants; every accessor returns value + `Provenance`.
  Unknown instance type or region → `FactorNotFound`, never a default.
- `core/ledger.py`: SQLite append-only (`INSERT` only; a trigger rejects `UPDATE`/`DELETE`), monotonic
  `seq`, `payload_sha256`, blobs by hash.

**Done when:** tests prove factor lookups for every instance type in SYNTHETIC_ESTATE §2, unknown types
raise, the ledger rejects updates, and a failed write raises.

## M1.5 — Model bake-off (parallel track)  `[ ]`

Decides the runtime model on evidence (ADR-0013). Needs M1 contracts; can run while M2–M6 proceed.

- `llm/ollama.py` minimal client (M7 extends it): `/api/chat`, `stream: false`, `format` = JSON schema,
  `think` from config, fence stripping, pydantic validation, one re-ask; returns the parsed object plus
  `prompt_eval_count`, `eval_count`, `total_duration`.
- `fixtures/llm_cases/*.json`: 10–12 cases derived from the seed-42 estate, each with input facts, allowed
  options and the accepted answers — patch decisions (GPU schedule vs rightsize, Graviton target, database
  target), a parameter repair from a canned `tofu plan` stderr, two ambiguous classifications, a narrative
  that must contain no numeric claims, and one trap that must be classified `not_waste`.
- `emissiongate bakeoff --models a,b,c --cases fixtures/llm_cases --out runs/bakeoff`: for each model, warm
  it, then run every case inside one `codecarbon` tracker block; write `BakeoffRow`s (DATA_CONTRACTS) to
  JSON and a Markdown table.
- The human runs `make bakeoff` (needs local Ollama). Apply ADR-0013's rule and append the table to its
  "Outcome" section.

**Done when:** the table exists for at least `gpt-oss:20b` and one Qwen model, the rule has been applied,
and `.env.example` reflects the outcome.

## M2 — Synthetic estate generator  `[ ]`

- `scripts/generate_estate.py` + `emissiongate estate --seed N [--terraform-out PATH]`.
- Produces everything in SYNTHETIC_ESTATE §1 with the shapes in §2 and §3; hourly series with
  seeded noise; month-end pattern for `monthend-close`; weekday pattern for `dev-api` and GPU requests.
- Synthetic prices file clearly labelled.
- Generator-side failure injection: `--inject corrupt-cur` (SYNTHETIC_ESTATE §6).

**Done when:** same seed → identical SHA-256 manifest; the generator copies `tofu/versions.tf` into the
estate; `tofu init -plugin-dir=.tofu-providers && tofu validate` passes on the generated `.estate/` (test
marked `tofu`) with no network; ground truth has 10 entries with 3 traps.

## M3 — Energy and emissions  `[ ]`

- `core/energy.py` implementing METHODOLOGY §1–§2; `core/grid.py` annual tier only for now.
- Golden tests G1–G4 to 3 decimal places.

**Done when:** all golden values match; every `EmissionRecord` carries provenance.

## M4 — Collector, policy, ranking  `[ ]`

- `tools/cur.py` (DuckDB over parquet), `tools/metrics.py`; `agents/collector.py` builds `Resource` +
  `Utilisation` (35-day window, `min_datapoints`, weekly activity mask).
- `core/policy.py` from `policy.yaml`: protected tags, required tags, fail-closed, advisory-only kinds,
  suppressions.
- `core/ranking.py`: candidates with savings (METHODOLOGY §3), `rank_carbon` and `rank_cost`.

**Done when:** on seed 42, `dr-standby` and `monthend-close` produce no candidates, `compliance-logs`
produces no expiration option, `orphaned-ebs` is an advisory, and the carbon order differs from the
cost order.

## M5 — Patch templates and validation  `[ ]`

- `core/patches/` with the five templates from INTERVENTIONS.md; registry; renderer returns full new
  file contents.
- `tools/tf.py`: in a temp copy of the estate, `tofu init -input=false -plugin-dir=$EG_TOFU_PLUGIN_DIR`,
  then `fmt -check`, `validate`, `plan -refresh=false -input=false -no-color`; returns `PlanResult` with a
  4 KB stderr tail. A missing mirror raises a clear error telling the human to run `make providers`.
- `run --inject bad-param` hook in the renderer (used by the demo and the repair-loop tests).

**Done when:** each template renders against the seed-42 estate and passes fmt/validate/plan
(`tofu`-marked tests); a deliberately bad parameter fails plan with a readable stderr tail.

## M6 — Orchestrator and offline mode end to end  `[ ]`  ← first demo-able state

- `orchestrator/machine.py` run-level + candidate-level machines (ARCHITECTURE §3–4),
  `checkpoint.py` (write before transition), `budget.py` (ceilings from policy.yaml).
- Agents wired with rule-based defaults; Gate 1 via `--approve` (records `$USER`).
- `report/` PR body template (numbers from core only) and a minimal HTML run report.
- `make demo-offline` works.

**Done when:** `make demo-offline` produces `runs/<id>/` with ledger, manifest, report and PR drafts;
`--resume` continues from a killed run; `tests/ground_truth/` passes the offline thresholds.

## M6.5 — PR gate  `[ ]`  ← the thesis, demo-able in CI

Spec: `docs/GATE.md`. Reuses core/, Strategist, Validator and ledger; adds a diff collector and a reporter.

- `tools/tf.py`: `plan_json(dir)` → `tofu init -plugin-dir`, `plan -refresh=false -out`, `show -json`.
- `agents/diff_collector.py`: pair base/head resources by address; extract carbon-relevant attributes
  (GATE §3 table); resolve region from provider configuration; schedules from `aws_autoscaling_schedule`.
- `core/projection.py`: METHODOLOGY §3b rules; assumed bands for new resources; golden tests G5–G7.
- `agents/reporter.py` + `report/templates/gate_comment.md.j2`: sticky comment (hidden marker
  `<!-- emissiongate-gate -->`), status per `policy.yaml → gate`, suggestions with diffs, not-quantified list,
  footer with the check's own runtime and "energy estimated".
- `emissiongate estate --telemetry-only` writes CUR and metrics without Terraform (the estate repo's CI uses it).
- `emissiongate gate --estate-dir <path> --base <ref> --head <ref> [--pr N --repo owner/name] [--post]`: without `--post` prints the comment
  (local pre-push use, `make gate`); with `--post` upserts the comment via httpx and exits 1 on
  `ack_required` unless the PR carries `eg/carbon-accepted` (reason = latest comment by the labeller).
- `runs/<run_id>/prediction.json` (`GatePrediction`, keyed by PR number + head SHA) next to
  `ledger.sqlite`; the workflow uploads the run directory as `emissiongate-gate-<PR>`, retention 90 days.
- Estate repo workflow `.github/workflows/emissiongate-gate.yml` (given) green on a test PR.

**Done when:** G5–G7 match to 3 decimals; on the estate repo, a PR adding 2 × g5.2xlarge fails with
"acknowledgement required" and passes after the label; a PR scaling `legacy-worker` passes with a warning
and a validated Graviton suggestion; a tags-only PR produces no comment; a PR with invalid HCL is "not
evaluated" and does not fail the check; the job never needs network beyond the cached provider mirror.

## M7 — Local LLM layer  `[ ]`

- `llm/client.py` protocol; extend the M1.5 `llm/ollama.py`: `think` level per call site from config
  (`EG_THINK_SMALL`/`EG_THINK_LARGE`), `options.temperature`, `options.num_ctx`; records model, think level,
  `prompt_eval_count`, `eval_count` (thinking included), `total_duration`. `message.thinking` is never
  stored in clear.
- Prompts: `plan_scan.j2`, `classify.j2`, `decide_patch.j2`, `repair_params.j2`, `narrative.j2`.
- Validation + one re-ask + deterministic fallback; numeric-claim scan on narrative.
- Repair loop ≤ 3 in the Validator; `FakeLLMClient` for tests.

**Done when:** `make demo` runs on a machine with the two models; with Ollama stopped the same command
completes in offline behaviour and the report says so; all LLM calls appear in the ledger with tokens.

## M8 — GitHub delivery and feedback loop  `[ ]`

- `tools/github.py` with httpx: get default branch SHA, create ref, put file contents, open PR, add
  labels, search open PRs by head branch, list closed PRs with `eg/*` labels; read-only for calibration:
  list artefacts, get a PR, download an artefact zip (GATE §7).
- Live mode: duplicate check before open. `emissiongate sync-feedback` writes `suppressions.yaml` and
  fetches gate predictions of merged PRs into `data/predictions/` (match on head SHA, never on merge SHA).

**Done when:** respx-mocked tests cover every endpoint; a manual `make demo-live` opens PRs on the
estate repo; closing one with `eg/false-positive` and re-running suppresses it; a squash-merged PR's
prediction is found by head SHA; an expired artefact yields `prediction_expired`, not an error.

## M9 — Live and snapshot grid tiers  `[ ]`

- `tools/grid_uk.py` (httpx; 5 s timeout, 2 retries): regional current + fw48h forecast + 7-day
  history for London (verify the region id with `/regional` before hard-coding).
- `emissiongate grid-snapshot` writes `fixtures/grid/uk_london_<date>.json`; commit one.
- `core/grid.py` tier resolution with provenance; `time_shift` uses snapshot/live.

**Done when:** tests use recorded fixtures only; `run --inject grid-offline` falls back and stamps the tier.

## M10 — Own footprint and run report  `[ ]`

- Wrap `run` in `codecarbon.EmissionsTracker(tracking_mode="machine", save_to_file=False)`; capture
  tracking method; `core/sci.py` per METHODOLOGY §5.
- The reported energy comes from a human-run `make demo` in a normal terminal — not from a run inside a
  coding agent's sandbox. The manifest records `approved_by` and the codecarbon tracking method.
- Run report: coverage, candidates by carbon vs by cost, advisories with reasons, PRs, reconciliation
  (with the synthetic caveat), SCI block, ledger summary (calls, tokens, retries, fallbacks).

- Calibration: for predictions in `data/predictions/` (or `run --predictions-dir`), once an address has
  `thresholds.min_datapoints` hourly points after deploy, compare predicted vs observed kgCO2e and add a
  `CalibrationRow` table to the report (GATE §7). Commit one recorded prediction for the demo estate to
  `fixtures/predictions/` so the offline demo shows the table; rows are marked `synthetic`.

**Done when:** report shows `measured` or `estimated` honestly; M is `not declared` unless configured;
payback ratio shown for proposed and merged separately.

## M11 — Scoring, comparison, polish  `[ ]`

- `emissiongate score` prints `Score` and writes `runs/<id>/score.json`.
- `make compare`: offline vs local on the same seed — precision, recall, first-attempt plan success,
  energy, tokens. This table is the "does the LLM earn its keep" slide.
- README results table filled from real runs. Rehearse DEMO_SCRIPT.md.

**Done when:** a clean clone → `make setup demo-offline score` works in under 10 minutes on a laptop.
