# Architecture

EmissionGate is one Python process that reads synthetic billing, utilisation and infrastructure-code
data, computes per-resource energy and emissions deterministically, and delivers reviewable pull
requests. A local open-weight LLM assists with choices, repair and narrative. Two humans gate the flow.

> This document describes the full design. Which parts are built in this submission and which are
> designed only: [README status table](../README.md#status-built-vs-designed).

All diagrams are Mermaid and render on GitHub. The one-page posters are exported to `docs/img/`
(`architecture-overview.png`, `architecture-sweep.png`, `architecture-gate.png`); the Mermaid diagrams are
the detailed, editable versions.

![Sweep mode](img/architecture-sweep.png)

![Gate mode](img/architecture-gate.png)

## 1. Context

```mermaid
flowchart LR
  subgraph Laptop["Laptop - one process"]
    EG["EmissionGate CLI"]
    OL["Ollama - local open-weight LLM"]
  end
  CUR[("Synthetic CUR<br/>parquet")] --> EG
  MET[("Synthetic metrics<br/>json")] --> EG
  TF[("Terraform HCL<br/>.estate/ or estate repo")] --> EG
  FAC[("Vendored CCF factors")] --> EG
  POL[("policy.yaml<br/>suppressions.yaml")] --> EG
  EG <-->|"structured JSON"| OL
  UK["UK Carbon Intensity API<br/>live, no key"] -.->|"eu-west-2 only"| EG
  EG -->|"branch + PR (live mode)"| GH["GitHub<br/>emissiongate-demo-estate"]
  ENG(["Platform engineer"]) -->|"Gate 1: approve scope"| EG
  ENG -->|"Gate 2: merge or reject"| GH
  GH -.->|"labels on closed PRs"| EG
```

Only two network destinations exist: the UK grid API (optional, falls back to a committed snapshot)
and GitHub (live mode only). The LLM runs on the same machine, so its energy is inside the
`codecarbon` measurement.

## 1b. Two modes, one engine

```mermaid
flowchart LR
  subgraph Triggers
    T1["Schedule or CLI<br/>emissiongate run"]
    T2["Pull request touching *.tf<br/>emissiongate gate (CI)"]
  end
  subgraph Engine["Shared engine - core/ + agents/"]
    Q["Quantifier<br/>factors · energy · tiers"]
    S["Strategist<br/>policy · ranking · templates"]
    V["Validator<br/>render · tofu plan · repair"]
    L[("Ledger")]
  end
  T1 -->|"billing + metrics + HCL"| Q
  T2 -->|"plan diff base vs head"| Q
  Q --> S --> V
  V -->|"sweep: opens a fix PR"| PR["Pull request on infra repo"]
  V -->|"gate: comment + check"| PR
  PR -->|"every infra PR, including the sweep's own"| T2
  PR -->|"merged: sync-feedback fetches<br/>the PR's prediction artefact"| CAL["Later sweep verifies<br/>predicted vs observed"]
  Q --- L
  V --- L
```

The **sweep** finds waste in what is already running and opens fix PRs. The **gate** checks every
infrastructure PR before merge — a human's or the sweep's — and posts the carbon delta. Details of the gate:
`docs/GATE.md` and §10–§11 below.

## 2. Components

```mermaid
flowchart TB
  CLI["cli.py"] --> ORCH["orchestrator/<br/>machine · checkpoint · budget"]
  ORCH --> PL["agents/planner"]
  ORCH --> CO["agents/collector"]
  ORCH --> QU["agents/quantifier"]
  ORCH --> ST["agents/strategist"]
  ORCH --> VA["agents/validator"]

  PL --> LLM["llm/ - Ollama client<br/>prompts/*.j2"]
  ST --> LLM
  VA --> LLM

  CO --> TOOLS["tools/<br/>cur · metrics · tf · grid_uk · github"]
  QU --> TOOLS
  VA --> TOOLS

  PL --> CORE
  CO --> CORE
  QU --> CORE
  ST --> CORE
  VA --> CORE

  subgraph CORE["core/ - deterministic, no network, no LLM"]
    EN["energy"]
    FA["factors"]
    GR["grid tiers"]
    PO["policy"]
    RA["ranking"]
    PA["patches/ templates + renderer"]
    LE["ledger"]
    SC["sci"]
    SG["scoring"]
  end

  ORCH --> REP["report/<br/>run report · PR body"]
```

| Component | Owns | Calls LLM | Side effects |
|---|---|---|---|
| Planner | scan order and depth within budget | small, 1 call (offline: rule) | none |
| Collector | resource graph + utilisation summaries | no | reads files |
| Quantifier | kWh, kgCO2e, provenance, CCFT reconciliation | no | reads files; grid API via tools |
| Strategist | candidates, guardrails, ranking, patch decision | small (classify), large (decide) | none |
| Validator | render, `tofu fmt/validate/plan`, bounded repair, PR draft/open | large (repair), small (narrative) | subprocess, GitHub |
| Ledger | append-only audit of everything | — | SQLite write |

## 3. Run-level state machine

```mermaid
stateDiagram-v2
  [*] --> SCOPED: Gate 1 approved (--approve)
  SCOPED --> COLLECTING
  COLLECTING --> QUANTIFIED: all sources ok
  COLLECTING --> QUANTIFIED: source failed (coverage reduced, logged)
  QUANTIFIED --> RANKED
  RANKED --> DELIVERING: candidates handed to per-candidate machine
  DELIVERING --> DONE: all candidates terminal
  COLLECTING --> BUDGET_STOPPED: ceiling hit
  DELIVERING --> BUDGET_STOPPED: ceiling hit
  SCOPED --> FAILED: ledger write failed / no factors
  COLLECTING --> FAILED: CUR unreadable
  DONE --> [*]
  BUDGET_STOPPED --> [*]
  FAILED --> [*]
```

`checkpoint.json` is written **before** each transition. `emissiongate run --resume <run_id>` continues
from the last checkpoint and does not re-spend completed LLM calls.

## 4. Candidate-level state machine

```mermaid
stateDiagram-v2
  [*] --> CANDIDATE
  CANDIDATE --> BLOCKED: guardrail tag / missing tag (fail closed)
  CANDIDATE --> ADVISORY: region_shift, decommission, below threshold
  CANDIDATE --> SUPPRESSED: matches suppressions.yaml
  CANDIDATE --> DECIDED: template + params chosen
  DECIDED --> RENDERED: core/patches renders HCL
  RENDERED --> VALIDATING
  VALIDATING --> DRAFTED: plan ok (offline/local)
  VALIDATING --> PR_OPEN: plan ok (live)
  VALIDATING --> REPAIRING: plan failed
  REPAIRING --> RENDERED: new params (attempt <= 3)
  REPAIRING --> ESCALATED: attempts spent
  BLOCKED --> [*]
  ADVISORY --> [*]
  SUPPRESSED --> [*]
  DRAFTED --> [*]
  ESCALATED --> [*]
  PR_OPEN --> [*]
```

After the run, `emissiongate sync-feedback` observes PRs on GitHub:

```mermaid
stateDiagram-v2
  PR_OPEN --> MERGED: human merges (Gate 2)
  PR_OPEN --> REJECTED: human closes with eg/* label
  REJECTED --> SUPPRESSION_RULE: written to suppressions.yaml
  MERGED --> VERIFIED: post-merge check (simulated T+7d in demo)
```

## 5. One candidate, end to end (local/live mode)

```mermaid
sequenceDiagram
  autonumber
  participant O as Orchestrator
  participant S as Strategist
  participant C as core/
  participant L as Ollama
  participant V as Validator
  participant T as tofu
  participant G as GitHub
  participant D as Ledger

  O->>S: ranked candidate (resource facts, kgCO2e/yr, allowed templates)
  S->>C: policy.check(resource)
  C-->>S: allowed templates + parameter options
  S->>L: decide(candidate, options) with JSON schema
  L-->>S: PatchDecision {template, params, rationale}
  S->>D: llm_call(model, tokens, ms) + decision
  S->>C: savings(template, params)  (deterministic)
  O->>V: decided candidate
  V->>C: patches.render(decision) -> HCL diff
  V->>T: fmt, validate, plan -refresh=false
  T-->>V: exit 1, stderr
  V->>L: repair(stderr tail, allowed params)
  L-->>V: new params
  V->>C: render again
  V->>T: plan
  T-->>V: exit 0
  V->>L: narrative(evidence)  (prose only)
  V->>C: build PR body (numbers from core, prose from LLM)
  V->>G: branch + commit + PR + labels (live only)
  V->>D: tool_call(github.pr_open), state PR_OPEN
```

## 6. The trust boundary

```mermaid
flowchart LR
  subgraph DET["Deterministic core - every published number"]
    E1["energy model"] --- E2["factors + provenance"]
    E3["policy engine"] --- E4["carbon ranking"]
    E5["patch renderer"] --- E6["ledger + SCI"]
  end
  subgraph LLMP["LLM perimeter - decisions and prose only"]
    L1["scan planning"]
    L2["ambiguous classification"]
    L3["patch decision"]
    L4["parameter repair"]
    L5["PR narrative"]
  end
  DET -->|"typed facts + allowed options"| LLMP
  LLMP -->|"schema-validated JSON, no numbers"| DET
```

The boundary is enforced three ways: `core/` cannot import `llm/` (test), LLM schemas have no numeric
fields for carbon/energy/cost (contracts), and PR bodies take every number from `core/` via the
template, with LLM prose inserted into a single `narrative` slot.

## 7. Deployment

```mermaid
flowchart LR
  subgraph Built["Built for the hackathon"]
    direction TB
    P["python -m emissiongate"]
    O["ollama serve"]
    F["files: data/ .estate/ runs/"]
  end
  subgraph Later["Production path - described, not built"]
    direction TB
    EB["EventBridge schedule"] --> SF["Step Functions - same state machine"]
    SF --> LA["Lambda per agent step"]
    LA --> S3["S3 + Athena ledger"]
  end
  Built -.->|"same contracts, different substrate"| Later
```

Why nothing is deployed: the agent's own footprint is a judged criterion. A laptop process that runs
for minutes and exits is smaller and more honest than idle cloud infrastructure kept up for a demo
(ADR-0009).

## 8. Human oversight points

| Point | Mechanism | Agent behaviour while waiting |
|---|---|---|
| Gate 1 — scope and budget | `--approve` flag (or interactive confirm); approver + time in ledger | run does not start |
| Gate 2 — merge | GitHub PR review | nothing changes until merged |
| Guardrail escalation | advisory entry in the run report (live: GitHub issue optional) | no PR is written |
| Repair exhausted | draft PR (live) or `ESCALATED` draft with plan error attached | stops after 3 attempts |
| Suppression override | human edits `suppressions.yaml` in git | rule stands until edited |

## 9. Failure handling

| Failure | Detected by | Response | Outcome |
|---|---|---|---|
| CUR partition malformed | schema check on load | skip partition, planner re-plans | coverage reduced, logged |
| Sparse metrics | datapoints < `min_datapoints` | resource marked insufficient | excluded, counted in coverage |
| UK API unreachable | timeout 5s, 2 retries | snapshot, then CCF annual | tier stamped on each figure |
| Plan fails | tofu exit code | repair ≤ 3, then escalate | recovered or `ESCALATED` |
| LLM invalid JSON | pydantic validation | 1 re-ask, then deterministic path | `fallback` event |
| Ollama down | connection error | whole run continues in offline behaviour | report says so |
| Guardrail hit | policy pre-decision | no diff written | `BLOCKED` / advisory |
| Duplicate open PR | GitHub search before open | skip, link existing | no duplicates |
| Budget exhausted | ledger counters | stop at checkpoint | `BUDGET_STOPPED`, resumable |
| Ledger write fails | assertion | abort | `FAILED` |

## 10. Gate mode — one pull request

```mermaid
sequenceDiagram
  autonumber
  participant E as Engineer
  participant G as GitHub
  participant A as Actions: emissiongate gate
  participant T as tofu (mirror only)
  participant C as core/
  participant D as Ledger
  E->>G: opens PR changing *.tf
  G->>A: pull_request event
  A->>T: init -plugin-dir, plan base and head, show -json
  T-->>A: two planned configurations
  A->>C: diff by address, project utilisation (observed or assumed band)
  C-->>A: per-resource and net kWh, kgCO2e, cost (synthetic), provenance
  A->>C: thresholds, flags, suggestions from templates
  A->>T: plan each suggestion on head (repair ≤ 3)
  A->>G: upsert sticky comment, set job result (pass / acknowledgement required)
  A->>D: ledger artefact + prediction record
  E->>G: applies a suggestion, or adds eg/carbon-accepted with a reason
  G->>A: synchronize / labeled event → re-run
  A->>G: check passes, records who accepted and why
  E->>G: merges (Gate 2 — human)
```

## 11. Gate check states

```mermaid
stateDiagram-v2
  [*] --> EVALUATING: PR opened or updated
  EVALUATING --> NOT_EVALUATED: plan failed / nothing quantifiable
  EVALUATING --> PASS: decrease or below warn
  EVALUATING --> PASS_WITH_WARNING: between warn and ack
  EVALUATING --> ACK_REQUIRED: at or above ack
  ACK_REQUIRED --> EVALUATING: new commit (e.g. suggestion applied)
  ACK_REQUIRED --> ACCEPTED: label eg/carbon-accepted + reason
  PASS --> [*]
  PASS_WITH_WARNING --> [*]
  NOT_EVALUATED --> [*]
  ACCEPTED --> [*]
```

The gate never pushes to the branch and never merges. `ACK_REQUIRED` is a failing check; whether that
blocks merging is the team's branch-protection setting.

