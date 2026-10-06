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
2. Within about a minute the **EmissionGate** check runs and posts one comment (updated in place on every
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
| at or above `ack_kg_co2e_yr` | ❌ "carbon acknowledgement required" | apply a suggestion, **or** add the label `eg/carbon-accepted` and a comment giving the reason → the check re-runs and passes, recording who accepted and why |
| plan failed or nothing quantifiable | ⚪ pass, "not evaluated" with the reason | nothing — other CI owns syntax errors |

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
| suggestion fails plan after 3 repairs | suggestion dropped, noted in the ledger | unaffected |

## 6. Security

- Runs on `pull_request`, with no secrets and a read-only token for fork PRs. For same-repo PRs the job
  has `pull-requests: write` to post the comment. For fork PRs, use the two-workflow pattern
  (`pull_request` builds the comment as an artefact; a `workflow_run` job with write permission posts it).
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
comment and the `eg/carbon-accepted` label event are not Actions data and do not expire, so the human
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
