# PR gate — carbon at merge time

The sweep (`emissiongate run`) finds waste in infrastructure that is **already running** and opens pull
requests to fix it. The gate (`emissiongate gate`) does the other half: it checks **every pull request
that changes infrastructure code**, before merge, and puts the carbon delta in front of the reviewer.

Same engine, two triggers. The gate reuses the factors, energy model, policy, patch templates, validator
and ledger. What is new is how it collects facts (from a plan diff, not from billing) and where it
reports (a PR comment and a check, not a new PR).

> This is the gate's specification, including parts designed but not built (`sync-feedback`, the
> calibration loop, the fork-PR workflow). How the built gate behaves on a real PR, and what another
> repository needs: [USING_THE_GATE.md](USING_THE_GATE.md). Status of everything:
> [README](../README.md#status-built-vs-designed).

## 1. How it behaves — one pull request, start to finish

1. An engineer opens or updates a PR on the infrastructure repo that touches `*.tf`.
2. Within about a minute the **`EmissionGate / carbon`** check is set and one comment is posted (updated in place on every
   push, never a new comment per push):
   - the net change in kWh/yr and kgCO2e/yr, and synthetic cost, for the PR as a whole
   - a row per changed resource: before, after, delta, and whether utilisation was **observed** (existing
     resource with telemetry) or **assumed** (new resource) — assumed figures are shown as a range
   - suggestions: lower-carbon alternatives from the same patch templates the sweep uses, each already
     validated with `tofu plan`, each with its own delta
   - anything it could not quantify, and why
3. The check result follows the thresholds in `policy.yaml → gate`:

| Net change | Check | What the human does |
|---|---|---|
| decrease, or below `warn_kg_co2e_yr` | ✅ pass | nothing |
| between `warn` and `ack` thresholds | ✅ pass, with a warning in the comment | reviewer reads it |
| at or above `ack_kg_co2e_yr` | ❌ "carbon acknowledgement required" | apply a suggestion, **or** add the label `eg/carbon-accepted` **and** submit a pull-request review (Comment or Approve) on the latest commit giving the reason; the same person labels and reviews, and needs write access → the check re-runs and passes, recording who accepted and why. A new push needs a new review (E1) |
| plan failed or nothing quantifiable | ❌ "not evaluated" with the reason (`gate.not_evaluated_conclusion: failure`, the shipped default; `neutral` is allowed, but GitHub counts neutral as passing a required check — ADR-0022) | fix the plan, or make it plannable |

4. The gate never pushes to the branch, never merges, and never decides. Whether a failing check blocks
   merging is the team's branch-protection choice. Merge is still Gate 2 — a human.
5. Every gate run writes a prediction record for the PR's head commit and keeps it as a workflow
   artefact. After merge, `sync-feedback` fetches the record for the commit that was merged, and a later
   sweep reports predicted vs observed — the calibration loop (§7).

## 2. Worked examples (golden values, METHODOLOGY §6)

| PR | Basis | Before → after (kgCO2e/yr) | Delta | Gate result |
|---|---|---|---|---|
| **G5** adds an ASG of 2 × g5.2xlarge, us-east-1, always on | assumed: CPU and GPU 50% (band 10–90%) | 0 → 683.517 (263.097–1103.937) | **+683.5** | ❌ acknowledgement required; suggests a schedule if the environment allows it |
| **G6** scales `legacy-worker` 6 → 10 × m5.2xlarge | observed 60% CPU; work held constant → 36% | 393.593 → 452.788 | **+59.2** | ✅ with warning; suggests Graviton (m7g.2xlarge × 10 → 220.571, **−232.2** vs the PR) |
| **G7** moves `nightly-etl` eu-west-2 → eu-north-1 | observed 80% CPU, 2 h/day | 27.446 → 0.720 | **−26.7** | ✅ pass; notes that a region move needs data-governance sign-off |
| EmissionGate's own GPU-schedule PR | observed | 401.484 → 143.388 | **−258.1** | ✅ pass — same engine, so this is a consistency check, not an independent one |

## 3. Pipeline

```
PR event (*.tf changed)
  → Planner      scope = changed files, budget for this check
  → Diff Collector  plan base and head (tofu plan -refresh=false -out, tofu show -json),
                    pair resources by address: added | removed | changed (carbon-relevant attributes)
  → Quantifier   energy and emissions for both sides; observed utilisation where telemetry exists,
                 assumption bands where it doesn't; provenance and tier on every figure
  → Strategist   thresholds and flags from policy; suggestions from patch templates on head resources
  → Validator    render each suggestion onto head, tofu plan; repair ≤ 3 (rule-based in CI)
  → Reporter     one sticky comment, the check result, ledger artifact, prediction record
```

### Carbon-relevant attributes

| Resource | Attributes read | Delta comes from |
|---|---|---|
| `aws_launch_template` + `aws_autoscaling_group` | `instance_type`, `desired_capacity`, `region` (provider) | type, count, region |
| `aws_autoscaling_schedule` | `recurrence`, `time_zone`, `desired_capacity` | hours on |
| `aws_instance` | `instance_type`, `region` | type, region |
| `aws_db_instance` | `instance_class`, `multi_az`, `allocated_storage` | class, storage |
| `aws_ebs_volume` | `size`, `type` | storage |
| `aws_s3_bucket_lifecycle_configuration` | transitions, expiration | storage class (≈ 0 under CCF) |
| anything else | — | listed as "not carbon-relevant" or "not quantified" |

Region comes from the resource's provider configuration in the plan JSON. Tags-only changes produce
"no carbon-relevant change" and no comment.

## 4. Projection rules (METHODOLOGY §3b)

- **Existing resource, telemetry available** → observed utilisation from the look-back window.
- **Capacity change** → total work held constant: `u_new = min(1, u_old × count_old / count_new)`.
- **Instance type change** → `u_new = min(1, u_old × vcpu_old / vcpu_new)` (same rule as `rightsize`).
- **New resource, no telemetry** → CPU at CCF's default 50% (`default_cpu_utilization`), GPU at 50% (no
  published default — stated as an assumption); shown as a range from 10% to 90%.
- **Schedules** → hours on from `aws_autoscaling_schedule` recurrences; none means 24×7.
- **Region** → annual tier (the same basis as sweep totals).
- **Removed resource** → its current energy becomes a negative delta.

## 5. Failure handling

| Failure | Response | Check |
|---|---|---|
| plan fails on base or head | comment "not evaluated: plan failed", stderr tail in the ledger | pass (neutral) |
| instance type or region not in the factors file | resource listed as "not quantified"; coverage shown | follows thresholds on what was quantified |
| no telemetry for a changed resource | treated as new: assumption band | as computed |
| provider mirror missing in CI | job fails loudly — a configuration error, not a carbon result | fail |
| GitHub API error posting the comment | 2 retries, then the job log carries the full comment | job result unchanged |
| evaluate artefact missing, malformed, or for another commit or repository | publish refuses it, ledgered; no comment | ❌ fail (fail closed, as a crashed job did before) |
| PR's current head is not the evaluated commit, or the PR lookup fails | nothing published (the newer push has its own run); ledgered | a required check stays pending |
| PR changes anything under `.github/` | evaluation not trusted (the PR's own workflow files ran it); ledgered; no comment | ❌ fail — a maintainer merges workflow changes on their own |
| PR targets a branch other than the default, or another open PR on the same commit does, or changes `.github/` | the check is per commit, so it cannot be trusted; ledgered; no comment | ❌ fail (ADR-0022) |
| GitHub API error creating the check run | ledgered; a required check stays pending, so merge stays blocked | — |
| suggestion fails plan after 3 repairs | suggestion dropped, noted in the ledger | unaffected |

## 6. Security

- **Two steps, so no token ever shares a process with planning (E1).**
  - *Evaluate* (`emissiongate-gate.yml`, on `pull_request` and `pull_request_review`): `contents: read`
    only and no `GITHUB_TOKEN`. `emissiongate gate --ci --config-from-base` plans base and head and
    writes `evaluation.json` (`GateEvaluation`, DATA_CONTRACTS), uploaded as `emissiongate-gate-<PR>`.
  - *Publish* (`emissiongate-publish.yml`, on `workflow_run`): the definition always comes from the
    default branch, and it never checks out or runs PR code. `emissiongate gate-publish` reads the
    artefact as untrusted data: size cap (2 MB), strict schema with extra fields refused, bound to
    the event's `workflow_run.head_sha` and repository; the PR number is used only if the API says
    that PR's head is this commit, and is refused when the PR changes `.github/`, since then its
    evaluate run used the PR's own workflow. Every open PR on the commit must target the default
    branch (`--base-branch`) and leave `.github/` unchanged, because a check run belongs to the
    commit. Non-finite or negative figures are refused. It
    re-derives the status in `core/verdict.py` with the default
    branch's `.emissiongate/policy.yaml`, never accepts an acceptance from the artefact, looks up the
    acknowledgement itself, re-renders the comment from the data, and sets the check run
    `EmissionGate / carbon` (`checks: write`). It keeps its own ledger with the artefact's SHA-256.
  - Fork PRs work the same way. Make `EmissionGate / carbon` the required check, not the evaluate job.
  - `gate --ci --post` (one job) still works but warns: it holds the token while planning.
- `tofu init -plugin-dir` from the vetted mirror means only the AWS provider is available. Untrusted HCL in
  a PR cannot pull in the `external` data source or any other provider that executes programs at plan time.
- Dummy credentials and `-refresh=false`: planning never contacts AWS.

## 7. Calibration loop — predict on the PR, verify after deploy

**What is kept.** Each gate run writes `runs/<run_id>/prediction.json` (`GatePrediction`,
DATA_CONTRACTS) next to `ledger.sqlite`. The workflow uploads the run directory as the artefact
`emissiongate-gate-<PR>` with `retention-days: 90`. The record is keyed by PR number and **head SHA**: the
gate runs on `pull_request` and never sees the merge commit, and squash or rebase merges create a new SHA.

**How the sweep gets it back** (`emissiongate sync-feedback`, M8; read-only, needs the human-exported
`GITHUB_TOKEN` with Actions read access — the gate itself needs no token for this):

1. `GET /repos/{o}/{r}/actions/artifacts?name=emissiongate-gate-<n>` for artefacts not yet synced
   (list all, filter by the `emissiongate-gate-` prefix, skip `expired: true`).
2. `GET /repos/{o}/{r}/pulls/{n}`: keep merged PRs only; note `head.sha` and `merged_at`.
3. Download the artefact whose `workflow_run.head_sha` equals `head.sha`
   (`GET /repos/{o}/{r}/actions/artifacts/{id}/zip`), verify `prediction.head_sha` inside it, and save it
   to `data/predictions/<pr>-<sha7>.json` (gitignored). No match → `no_prediction`.

**When it can be compared.** After deploy, once each address has at least `policy.yaml →
thresholds.min_datapoints` hourly points (500, about three weeks) inside the look-back window. The run
report adds a calibration table: predicted range and central value, observed value, inside the band or
not, error against the central value, per basis (`assumed`, `observed_projected`).

**Expiry is a hard limit.** GitHub deletes artefacts after at most 90 days on public repositories, and
from 1 October 2026 check runs follow the same retention. So `sync-feedback` must run within 90 days of
merge; a prediction that expired is listed as `prediction_expired`, never dropped silently. The PR
comment, the `eg/carbon-accepted` label and the acknowledging review are not Actions data and do not expire, so the human
acceptance record outlives the artefact. The production path copies predictions into the S3 ledger at
merge instead (ARCHITECTURE §7, production path).

**Offline.** `run --predictions-dir fixtures/predictions` reads recorded predictions, so
`make demo-offline` shows the calibration table without network.

This is the evidence for — or against — the 50% default for new resources, and the place to tune it
per environment later.

## 8. Footprint of the gate itself

No LLM in CI: decisions use the rule-based defaults and the comment uses the deterministic template. The
check is a plan of two configurations and some arithmetic — seconds of CPU per PR. The provider mirror
is restored from the Actions cache, so no PR re-downloads the AWS provider. Energy on hosted runners can
only be estimated (no hardware counters) and is reported as such in the comment footer. Run locally with
`make gate` and a local model, the same check can add LLM narrative; the numbers do not change.

## 9. Related work

Carbonifer estimates carbon from Terraform plans; Infracost puts cost estimates in pull requests.
EmissionGate's gate differs in four ways: observed utilisation for changed resources instead of nameplate
assumptions, validated lower-carbon suggestions from shared templates, a human acknowledgement step with
an audit trail, and calibration of its own predictions by the sweep. Neither tool's code is used.

## 10. Limitations

- Assumed utilisation for new resources is the weakest number the system publishes — always a range,
  always labelled, and calibrated after deploy rather than defended up front.
- On the synthetic estate, calibration compares one model against telemetry generated by another
  model. It proves the loop works, not that the 50% default is right. Only real telemetry can do that.
- Predictions live in Actions artefacts, which expire after 90 days on public repositories (§7).
- Plans run against empty state: the gate compares configurations, not live infrastructure.
- Only resource types and regions in the factors file are quantified; the rest are listed, not guessed.
