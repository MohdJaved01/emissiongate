# EmissionGate

**Carbon at merge time.** An agent that puts the carbon cost of cloud and AI infrastructure into the pull
request: it finds waste in running infrastructure and drafts the fix as a PR, and it checks every
infrastructure PR before merge and posts its kgCO2e delta with validated lower-carbon suggestions.
Humans decide; the agent cannot apply, merge or delete anything.

> **Demo video (4 min, agent running):** TODO-VIDEO-LINK
>
> **Live gate example:** [emissiongate-demo-estate PR #1](https://github.com/MohdJaved01/emissiongate-demo-estate/pull/1) (a PR adding 2 × g5.2xlarge, with the gate's comment). Its red ❌ `gate` check is the
> intended result: +683.5 kgCO2e/yr is above the 100 kg threshold, so the check fails until a human
> comments a reason and adds `eg/carbon-accepted` (or commits the suggestion). Merging stays a human
> decision.
>
> **Sample output without installing anything:** [docs/sample-run/](docs/sample-run/) — the HTML run
> report and the four PR drafts from today's local-LLM run (synthetic).
>
> All data is **synthetic** or public. No customer, confidential or personal data is used.
> *Prompt, Plan, Preserve* hackathon — Green IT (Green AI / carbon accounting).

| Deliverable | Where |
|---|---|
| Agent design document (architecture, decision points, oversight, failure handling) | [docs/AGENT_DESIGN.md](docs/AGENT_DESIGN.md) |
| Pitch deck (10 slides) | [docs/EmissionGate-pitch.pdf](docs/EmissionGate-pitch.pdf) · [.pptx](docs/EmissionGate-pitch.pptx) |
| Augmentation log (AI usage across the lifecycle) | [docs/augmentation-log.md](docs/augmentation-log.md) |
| Demo video | link above |

**Built with:** Claude Code (all code in this repository) and Claude (design and documents). Codex licences
arrived late in the hackathon; Codex built and checked an early scaffold prototype, then the submission was
built with Claude Code. Details: [augmentation log](docs/augmentation-log.md) ·
[ADR-0016](docs/adr/0016-claude-code-builds-submission.md).

## The problem

Infrastructure emissions are committed when infrastructure code merges, but nobody sees carbon at that
moment. Cloud carbon reports arrive monthly, by region, never per resource or per change. An idle GPU
fleet burns electricity for months before anyone connects it to a decision, and cost-ranked tools
prioritise a different list from carbon-ranked ones.

## Two modes, one engine

![Two modes, one engine](docs/img/architecture-overview.png)

- **Sweep** — reads billing, utilisation and Terraform, computes kWh and kgCO2e per resource, refuses
  anything a guardrail protects, ranks the rest by carbon, renders a fix from a fixed set of templates,
  proves it with `tofu plan`, and drafts a pull request with the numbers and evidence.
- **Gate** — on every PR that changes `*.tf`, plans base and head, computes the carbon delta per resource
  and posts one comment with lower-carbon suggestions that are themselves proven to plan. Above
  100 kgCO2e/yr the check fails until a human commits a suggestion or acknowledges the increase with a
  reason. Spec: [docs/GATE.md](docs/GATE.md).

## Setup

Runs on Linux, macOS or **Windows via WSL2 (Ubuntu 24.04)**. Nothing is deployed and no cloud account is
needed.

| Need | Version | Install |
|---|---|---|
| Python | 3.12+ | Ubuntu 24.04: `sudo apt install python3-venv python3-pip` |
| make, git | any | `sudo apt install make git` |
| OpenTofu | 1.8+ | [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/) |
| Ollama + `gpt-oss:20b` | optional, for the LLM tier | [ollama.com](https://ollama.com); about 14 GB, needs ~16 GB free RAM |

```bash
git clone https://github.com/MohdJaved01/emissiongate && cd emissiongate
make setup        # virtualenv, dependencies, .env from .env.example
make providers    # AWS provider once into .tofu-providers/ — after this, runs need no network
```

**Native Windows (how the submission was built, ADR-0017)** — no WSL or `make` needed, PowerShell:

```powershell
winget install astral-sh.uv OpenTofu.Tofu   # optional: winget install Ollama.Ollama
uv venv --python 3.12 .venv; uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
cd tofu; tofu providers mirror ..\.tofu-providers; cd ..
.venv\Scripts\emissiongate estate --seed 42
.venv\Scripts\emissiongate run --mode offline --seed 42 --approve
.venv\Scripts\emissiongate score
.venv\Scripts\emissiongate run --mode local --seed 42 --approve   # with Ollama + gpt-oss:20b
```

GitHub Actions on Ubuntu runs the real `make` targets on every push (`.github/workflows/ci.yml`).

## Run

```bash
make demo-offline   # generate the synthetic estate (seed 42) and run the sweep — no LLM, no keys
make score          # precision, recall and trap violations against the seeded ground truth
```

Open `runs/<run_id>/report.html`. Then, optionally, with the local model:

```bash
ollama pull gpt-oss:20b
make demo           # same pipeline; the model chooses parameters and writes PR narrative
```

**The gate.** See it on GitHub at the live example linked above, or run it locally against the demo
estate:

```bash
make estate      # telemetry in data/ gives existing resources their observed utilisation
git clone https://github.com/MohdJaved01/emissiongate-demo-estate ../estate
.venv/bin/emissiongate gate --estate-dir ../estate --base main --head origin/demo/add-gpu-fleet
# Windows: .venv\Scripts\emissiongate gate --estate-dir ..\estate --base main --head origin/demo/add-gpu-fleet
```

It needs the provider mirror from `make providers`.

It prints the comment the PR would get. In the estate repo, `.github/workflows/emissiongate-gate.yml`
runs the same command on every pull request and posts the comment. The estate repository's contents
are reproducible from this one: `python scripts/build_estate_repo.py OUT_DIR` (the workflow source is in
[`estate-repo/`](estate-repo/)).

### What you will see

| Output | Content |
|---|---|
| `runs/<id>/report.html` ([sample](docs/sample-run/report.html)) | per-resource kgCO2e with provenance, carbon vs cost ranking, refused and advisory items with reasons, PR drafts, the agent's own energy and kgCO2e |
| `runs/<id>/prs/*.md` ([sample](docs/sample-run/prs/gpu-inference.md)) | each PR body as it would appear on GitHub |
| `runs/<id>/ledger.sqlite` | every state transition, tool call and LLM call with tokens and timings |
| gate comment | net kgCO2e/yr per changed resource, assumption range, suggestions, check status |

## Sample data

`make estate` (run by `make demo-offline`) generates everything from `--seed 42`; the same seed gives
byte-identical files. Generated files are not committed — they appear in `data/` and `.estate/`.

| Data | Content |
|---|---|
| Billing | CUR-shaped parquet, hourly, 35 days, synthetic prices |
| Utilisation | hourly CPU, GPU and memory per resource |
| Terraform | 10 resource groups, one `.tf` file each, dummy credentials, plans offline |
| Ground truth | the expected decision for each resource, used by `make score` |

The estate contains real-looking waste — an idle staging GPU fleet, an always-on dev API, x86 workers
that could run on Graviton, an oversized database, an unattached EBS set, a nightly batch — **and three
traps** that look like waste but must be refused: a DR standby, a month-end batch that is idle 27 days
a month, and a regulatory log bucket that must never get an expiry rule. Details:
[docs/SYNTHETIC_ESTATE.md](docs/SYNTHETIC_ESTATE.md).

Coefficients come from Cloud Carbon Footprint (Apache-2.0), vendored at commit `f584c549`
([factors/](factors/)). Grid data for time-shifting comes from a committed UK Carbon Intensity snapshot
(CC BY 4.0).

## Results

Worked examples from the published coefficients. The test suite reproduces each to 3 decimal places
([METHODOLOGY.md §6](docs/METHODOLOGY.md)).

| Change | Before → after (kgCO2e/yr) | Delta |
|---|---|---|
| Schedule the idle staging GPU fleet (4 × g5.2xlarge) to 60 h/week | 401.5 → 143.4 | **−258.1** |
| Move 6 × m5.2xlarge workers to Graviton (m7g) | 393.6 → 175.0 | **−218.6** |
| Rightsize the reporting database (db.r5.4xlarge → db.r5.xlarge) | 138.8 → 42.2 | **−96.6** |
| Schedule the always-on dev API (12 × m5.large) to weekday 09–19 | 70.6 → 35.9 | **−34.7** |
| Gate: PR adds 2 × g5.2xlarge, 24×7, no history (assumed 50% load, range 10–90%) | 0 → 683.5 (263.1–1,103.9) | **+683.5**, acknowledgement required |
| Gate: PR scales m5.2xlarge 6 → 10; same work spread over more instances (u 0.60 → 0.36) | 393.6 → 452.8 | **+59.2**, warning; suggestion m7g × 10: **−232.2** |

The four sweep rows are the four PR drafts of today's run; their published deltas add to 608.0, and the
run's own total (608.1) is the sum of the unrounded values.

From today's runs on seed 42 (run ids `20261005T090230Z-offline-s42` and `20261005T091433Z-local-s42`;
the local run's report and PRs are in [docs/sample-run/](docs/sample-run/)), Windows laptop, Intel Core
Ultra 9, CPU inference:

| Metric | Offline | Local LLM (`gpt-oss:20b`) |
|---|---|---|
| Precision / recall vs ground truth | 1.00 / 0.80 | 1.00 / 0.80 |
| Trap violations | 0 | 0 |
| PR drafts (all plans passed first attempt) | 4 | 4 |
| kgCO2e/yr in proposed fixes (proposed, not merged) | 608.1 | 608.1 |
| Agent energy per run (CodeCarbon) | 0.000360 kWh, **estimated** | 0.005228 kWh, **estimated** |
| Agent gCO2e per run (I = 713 g/kWh, CodeCarbon, India) | 0.26 g | 3.73 g |
| Payback ratio (proposed fixes ÷ run) | ≈ 2.4 million × | ≈ 163,000 × |
| LLM calls / tokens / fallbacks | 0 / 0 / 0 | 8 / 6,624 / 0 (8 of 8 schema-valid first try) |

Recall is 0.80 because the fifth "act" resource, the nightly ETL, saves only 0.035 kgCO2e/yr by
time-shifting on the committed London snapshot — below the 5 kg threshold, so it is reported as an
advisory instead of a PR. Energy is labelled **estimated**: CodeCarbon reads CPU energy from hardware
counters on this laptop (Windows EMI) but models RAM power (45–62% of the total). The model added about
0.005 kWh per run and chose the same parameters as the rules; on this estate its value is the
narrative, not different decisions. These runs were launched by the coding agent on the build laptop,
not in a sandbox; a human-run `make demo` produces the same report for independent figures.

Per-resource figures are tens to hundreds of kgCO2e per year. That is what the coefficients say, and the
project reports it as it is rather than extrapolating.

## Status: built vs designed

This was built in a hackathon. The design covers more than the code does; this table says which is which.

| Capability | Milestone | Status |
|---|---|---|
| Synthetic estate with traps and ground truth | M2 | built — byte-identical per seed, plans offline |
| Energy and emissions model, golden values G1–G7 | M3, M6.5 | built — G1–G4 (M3) and G5–G7 (M6.5) tested to 3 decimals |
| Guardrails, carbon ranking, five fix templates, `tofu plan` validation | M4–M5 | built |
| Sweep end to end, offline, with PR drafts, report and scoring | M6 | built (`--resume` not built) |
| Agent's own energy and kgCO2e in the report (CodeCarbon) | M10 (part) | built — labelled estimated (RAM is modelled) |
| PR gate in GitHub Actions with comment, check and acknowledgement label | M6.5 | built |
| Local LLM for parameter choice and PR narrative, offline fallback | M7 (part) | built (scan planning and classification not built) |
| Model bake-off (gpt-oss vs Qwen, measured) | M1.5 | designed, not built |
| Opening real PRs and learning from rejection labels | M8 | designed, not built |
| Live UK grid API (a committed snapshot is used instead) | M9 | snapshot fetcher built and one real snapshot committed; live tier at run time not built |
| Calibration of gate predictions against observed load | M10 (part) | designed, not built |

## Known limitations

- **Estimates, not meter readings.** Per-resource energy is modelled from published coefficients.
- **New resources are assumed.** A resource with no history gets CCF's 50% utilisation default, always
  shown as a 10–90% range and labelled `assumed`. It is the weakest number the system publishes.
- Location-based emissions only; no market-based figures; no embodied carbon for cloud hardware.
- **Synthetic estate.** Precision is measured against ground truth the team designed: it shows the scoring
  works, not that the agent generalises to real estates.
- `tofu plan` runs against empty state: it proves the HCL is valid, not what AWS would change.
- AWS only; time-shifting uses UK grid data for eu-west-2 only, from a snapshot.
- The agent's own energy is labelled **estimated**: CodeCarbon reads CPU counters where the machine has
  them (Windows EMI here) but models RAM power, and hosted CI runners expose no counters at all.
- See the status table for designed-but-not-built capabilities.

## Agent sustainability choices

- Every number comes from deterministic code; the model only chooses among allowed options and writes
  prose, so it runs rarely and briefly.
- One local open-weight model, OpenAI's `gpt-oss-20b` (Apache-2.0, about 3.6B active parameters per token),
  with low reasoning for narrative and medium for patch decisions — its energy is inside the
  measurement, not assumed.
- No LLM in CI: the gate is two offline plans plus arithmetic (about 30 s of tofu on a laptop).
- Fixed templates instead of generated code; hard budgets on calls, tokens, repairs, time and PRs.
- An offline mode with the same pipeline, so the LLM's marginal value and marginal energy can be compared.
- Nothing deployed: one process that runs and exits; providers come from a local mirror, not re-downloaded.

## Repository map

```
src/emissiongate/   cli, orchestrator, agents, core (deterministic), llm, tools, report, estate generator
factors/            vendored Cloud Carbon Footprint coefficients
fixtures/grid/      committed UK grid-intensity snapshot (CC BY 4.0)
policy.yaml         guardrails, thresholds, gate settings
tofu/versions.tf    provider constraint for the mirror and the estate
estate-repo/        workflow, README and .gitignore of the demo estate repository
scripts/            estate-repo builder, agent-file checker
docs/               design document, pitch deck, augmentation log, methodology, ADRs, sample run
tests/              unit, golden values, ground truth (sweep and gate scenarios)
```

More: [Architecture](docs/ARCHITECTURE.md) · [Methodology](docs/METHODOLOGY.md) · [PR gate](docs/GATE.md) ·
[Interventions](docs/INTERVENTIONS.md) · [Data contracts](docs/DATA_CONTRACTS.md) ·
[Build plan](docs/BUILD_PLAN.md) · [Decisions](docs/adr/README.md) · [Demo script](docs/DEMO_SCRIPT.md) ·
[Developing with Codex or Claude Code](docs/DEVELOPING.md) · [Third-party components](THIRD_PARTY.md)

## Licence

Apache-2.0.
