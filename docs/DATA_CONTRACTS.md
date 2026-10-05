# Data contracts

These models are the interface between every component. Milestone M1 copies this block into
`src/emissiongate/contracts.py` verbatim, then tests it. Change the contracts here first, then the code.

Rules: every model is frozen; units are in field names; money is synthetic; no LLM-facing model has a
numeric carbon, energy or cost field.

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# ---------- provenance ----------

GridTier = Literal["live", "snapshot", "annual"]


class Provenance(Frozen):
    source: str  # "ccf@f584c54", "uk-carbon-intensity-api", "fixture:uk_london_2026-09-28"
    version: str
    tier: GridTier | Literal["vendored", "measured", "estimated", "synthetic"]
    retrieved_at: datetime | None = None


# ---------- inventory ----------

ResourceKind = Literal["ec2_asg", "ec2", "rds", "ebs", "s3", "batch"]


class Resource(Frozen):
    resource_id: str  # synthetic, e.g. "eg-gpu-inference"
    kind: ResourceKind
    region: str
    instance_type: str | None = None
    count: int = 1  # instances in an ASG / fleet
    storage_tb: float | None = None
    storage_class: str | None = None  # "gp3", "STANDARD", "GLACIER_IR"
    attached: bool | None = None  # EBS only
    tags: dict[str, str]
    tf_file: str | None = None  # relative to estate root
    tf_address: str | None = None  # "aws_autoscaling_group.gpu_inference"
    schedule_expression: str | None = None  # batch only, "cron(0 2 * * ? *)"
    synthetic: Literal[True] = True


class Utilisation(Frozen):
    resource_id: str
    window_days: int
    datapoints: int
    cpu_avg: float | None = None  # 0..1
    cpu_p95: float | None = None
    gpu_avg: float | None = None
    active_hour_share: float | None = None  # share of hours above idle threshold
    active_mask_168: list[bool] | None = None  # hour-of-week activity, Monday 00:00 UTC first
    sufficient: bool
    reason: str | None = None
    running_hour_share: float | None = None  # share of window hours with instances running
    cpu_avg_off_mask: float | None = None  # mean CPU outside the active mask (schedule saving)
    gpu_avg_off_mask: float | None = None
    weekly_regularity: float | None = None  # share of weeks whose activity matches the mask
    mask_coverage: float | None = None  # share of active hours inside the mask


# ---------- quantification ----------


class EnergyBreakdown(Frozen):
    cpu_watts: float
    gpu_watts: float
    memory_watts: float
    storage_kwh_yr: float = 0.0
    network_kwh_yr: float = 0.0


class EmissionRecord(Frozen):
    resource_id: str
    kwh_yr: float
    kg_co2e_yr: float
    g_per_kwh: float
    pue: float
    breakdown: EnergyBreakdown
    provenance: list[Provenance]
    ledger_event_id: int


# ---------- strategy ----------

Intervention = Literal["rightsize", "schedule", "graviton", "storage_tier", "time_shift"]
AdvisoryKind = Literal[
    "region_shift", "decommission", "guardrail", "below_threshold", "insufficient_evidence"
]


class ParamOption(Frozen):
    name: str  # "target_instance_type"
    allowed: list[str]  # always strings; the renderer parses them


class Candidate(Frozen):
    candidate_id: str  # f"{resource_id}:{intervention}"
    resource_id: str
    intervention: Intervention
    options: list[ParamOption]  # what the decision may choose from
    default_params: dict[str, str]  # the rule-based choice (offline mode uses this)
    kg_co2e_saved_yr: float
    kwh_saved_yr: float
    usd_synthetic_saved_yr: float
    rank_carbon: int
    rank_cost: int
    confidence: Literal["high", "medium", "low"]


class Advisory(Frozen):
    resource_id: str
    kind: AdvisoryKind
    reason: str
    blocked_by: list[str] = Field(default_factory=list)  # e.g. ["tag:Role=DR"]
    kg_co2e_saved_yr: float | None = None


# ---------- LLM-facing (no numeric carbon/energy/cost fields, by rule) ----------


class ScanPlan(Frozen):
    order: list[ResourceKind]
    deep_metrics_for: list[ResourceKind]
    rationale: str = Field(max_length=400)


class Classification(Frozen):
    resource_id: str
    label: Literal["waste", "not_waste", "unsure"]
    rationale: str = Field(max_length=400)


class PatchDecision(Frozen):
    candidate_id: str
    template: Intervention
    params: dict[str, str]  # keys must match Candidate.options names; values must be in allowed
    rationale: str = Field(max_length=400)


class Narrative(Frozen):
    summary: str = Field(max_length=600)  # prose only; numbers are re-inserted by template
    risks: list[str] = Field(max_length=5)


# ---------- validation and delivery ----------


class PlanResult(Frozen):
    ok: bool
    command: str
    exit_code: int
    stderr_tail: str = ""  # last 4 KB
    attempt: int


class PullRequestDraft(Frozen):
    candidate_id: str
    branch: str  # "emissiongate/<candidate_id>"
    title: str
    body_md: str
    files: dict[str, str]  # path -> full new content
    labels: list[str]
    status: Literal["drafted", "opened", "escalated", "skipped_duplicate"]
    url: str | None = None


# ---------- ledger ----------

EventKind = Literal[
    "transition", "tool_call", "llm_call", "decision", "fallback", "error", "human_gate", "budget"
]


class LedgerEvent(Frozen):
    run_id: str
    seq: int
    ts: datetime
    state: str
    agent: str | None = None
    kind: EventKind
    tool: str | None = None
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int | None = None
    attempt: int | None = None
    payload_sha256: str | None = None
    detail: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


# ---------- run outputs ----------


class SciResult(Frozen):
    energy_kwh: float
    energy_label: Literal["measured", "estimated"]
    tracking_method: str  # from codecarbon
    grid_g_per_kwh: float
    grid_source: str
    embodied_kg_co2e: float | None  # None = not declared
    kg_co2e_per_run: float
    kg_co2e_per_accepted_recommendation: float | None
    payback_ratio_merged: float | None
    payback_ratio_proposed: float | None


class RunManifest(Frozen):
    run_id: str
    mode: Literal["offline", "local", "live"]
    seed: int
    started_at: datetime
    finished_at: datetime | None
    final_state: Literal["DONE", "BUDGET_STOPPED", "FAILED"] | None
    approved_by: str
    coverage: float  # resources quantified / resources in scope
    counts: dict[str, int]  # candidates, advisories, drafted, opened, escalated, blocked
    llm: dict[str, int]  # calls, prompt_tokens, completion_tokens, fallbacks
    repair_attempts: int
    first_attempt_plan_success: float | None
    factors_version: str
    models: dict[str, str]  # {"small": "gpt-oss:20b@low", "large": "gpt-oss:20b@medium"}
    tofu_version: str | None
    sci: SciResult | None


# ---------- PR gate (docs/GATE.md) ----------

UtilisationBasis = Literal["observed", "observed_projected", "assumed"]


class ResourceChange(Frozen):
    address: str  # "aws_autoscaling_group.legacy_worker"
    change: Literal["added", "removed", "changed", "unchanged"]
    carbon_relevant: bool
    before: dict[str, str] = Field(
        default_factory=dict
    )  # instance_type, desired_capacity, region, ...
    after: dict[str, str] = Field(default_factory=dict)


class Projection(Frozen):
    address: str
    basis: UtilisationBasis
    kg_co2e_yr_before: float
    kg_co2e_yr_after: float  # central value
    kg_co2e_yr_after_low: float | None = None  # assumed basis only
    kg_co2e_yr_after_high: float | None = None
    kg_co2e_yr_before_low: float | None = None  # assumed basis only (same band as after)
    kg_co2e_yr_before_high: float | None = None
    kwh_yr_delta: float
    usd_synthetic_yr_delta: float
    provenance: list[Provenance]
    quantified: bool = True
    reason: str | None = None  # why not quantified


class GateSuggestion(Frozen):
    address: str
    template: Intervention
    params: dict[str, str]
    kg_co2e_yr_delta_vs_head: float
    plan_ok: bool
    diff: str  # unified diff against head, shown in the comment
    basis: UtilisationBasis = "observed"
    kg_co2e_yr_delta_low: float | None = None  # assumed basis only
    kg_co2e_yr_delta_high: float | None = None
    ledger_event_id: int | None = None


class GateResult(Frozen):
    pr_number: int
    base_sha: str
    head_sha: str
    status: Literal["pass", "pass_with_warning", "ack_required", "accepted", "not_evaluated"]
    net_kg_co2e_yr: float
    net_kg_co2e_yr_low: float
    net_kg_co2e_yr_high: float
    changes: list[ResourceChange]
    projections: list[Projection]
    suggestions: list[GateSuggestion]
    accepted_by: str | None = None
    accepted_reason: str | None = None
    ledger_run_id: str
    projection_event_id: int | None = None  # ledger event holding every projection


class GatePrediction(Frozen):
    """runs/<run_id>/prediction.json — kept as the artefact emissiongate-gate-<PR> (GATE §7)."""

    repo: str  # "owner/name"
    pr_number: int
    head_sha: str  # the commit predicted; the merge SHA may differ (squash/rebase)
    base_sha: str
    created_at: datetime
    factor_version: str
    projections: list[Projection]  # assumed rows carry low/high


class CalibrationRow(Frozen):
    pr_number: int
    head_sha: str
    address: str
    basis: UtilisationBasis
    status: Literal["ok", "insufficient_data", "prediction_expired", "no_prediction"]
    predicted_kg_co2e_yr: float | None = None
    predicted_low: float | None = None
    predicted_high: float | None = None
    observed_kg_co2e_yr: float | None = None
    within_band: bool | None = None  # assumed basis only
    error_pct: float | None = None  # (observed - predicted) / predicted × 100
    synthetic: bool  # True on the demo estate: proves the loop, not the default


# ---------- model bake-off (ADR-0013) ----------


class BakeoffRow(Frozen):
    model: str  # "gpt-oss:20b"
    think: str  # "low" | "medium" | "high" | "off"
    cases: int
    schema_valid_first_try: float  # 0..1
    schema_valid_after_reask: float
    decision_agreement: float  # share of cases whose answer is in the accepted set
    prompt_tokens: int
    completion_tokens: int  # includes thinking tokens
    median_latency_ms: int
    energy_kwh: float | None
    energy_label: Literal["measured", "estimated"] | None


# ---------- ground truth (generator output, scoring input) ----------


class GroundTruthEntry(Frozen):
    resource_id: str
    expected: Literal["act", "refuse", "refuse_or_tier", "advisory"]
    accepted_interventions: list[Intervention] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)  # e.g. ["expiration", "deletion"]
    trap: bool
    note: str


class Score(Frozen):
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float | None
    recall: float | None
    trap_violations: list[str]
    carbon_rank_order: list[str]
    cost_rank_order: list[str]
```

## Validation rules outside the type system

- 5 Oct 2026 (M6.5 invariant review): `Projection` gained `kg_co2e_yr_before_low/high` so a removal or
  a change to a resource without telemetry is published as a range on both sides; `GateSuggestion`
  gained `basis`, a delta range and its ledger event id; `GateResult` gained `projection_event_id`.

- `Utilisation` gained five optional fields on 5 Oct 2026 (M4): `running_hour_share`,
  `cpu_avg_off_mask`, `gpu_avg_off_mask`, `weekly_regularity`, `mask_coverage`. `schedule` savings use the
  off-mask utilisation (METHODOLOGY §3); `mask_coverage` stops a monthly pattern from passing as weekly.

- `PatchDecision.params` keys ⊆ candidate option names, values ∈ `allowed`. Anything else → re-ask once,
  then use `Candidate.default_params`.
- `Narrative` text is scanned for digits adjacent to `kg`, `kWh`, `t`, `%`, `$`, `USD`, `CO2`. Any match →
  discard the narrative and use the templated summary. Log `kind=fallback, detail.reason=numeric_claim`.
- `LedgerEvent.detail` holds scalars only; large payloads are stored by hash in `runs/<id>/blobs/`.
