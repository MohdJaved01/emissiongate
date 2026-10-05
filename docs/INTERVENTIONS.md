# Interventions (patch templates)

The model never writes HCL. It chooses a template and parameter values from allowed lists; the
renderer in `src/emissiongate/core/patches/` produces the change. Offline mode uses each template's
rule-based default.

Every template must: declare its parameters and allowed values, provide a deterministic default,
provide a savings function (METHODOLOGY §3), render a minimal diff against the estate's HCL shape
(SYNTHETIC_ESTATE §3), and pass `tofu fmt -check`, `tofu validate` and `tofu plan -refresh=false`.

| Template | Applies to | Parameters (allowed values) | Rule-based default | Guard notes |
|---|---|---|---|---|
| `rightsize` | `ec2_asg`, `rds` | `target_instance_type` ∈ smaller sizes, same family and architecture, whose projected p95 ≤ `rightsize_target_p95_max` | smallest size that satisfies the p95 limit | blocked by `Role=DR`, `Criticality=prod-critical` |
| `schedule` | `ec2_asg` with a regular weekly activity mask | `on_cron`, `off_cron` from observed mask; `time_zone` ∈ {region default}; `min_on` ∈ {current desired} | on 30 min before first active hour, off 30 min after last, weekdays | requires `Environment` ∈ {dev, test, staging} **or** `ScheduleOk=true` |
| `graviton` | `ec2_asg` on x86 with an arm64 equivalent in the factors file | `target_instance_type` ∈ arm64 equivalents of the same size; `image_param` ∈ {`ami_arm64`} | same size in the newest Graviton family available | PR body must state "requires arm64 build" |
| `storage_tier` | `s3` without lifecycle rules | `transition_days` ∈ {30, 90, 180}; `storage_class` ∈ {`GLACIER_IR`, `DEEP_ARCHIVE`} | 90, `GLACIER_IR` | `Retention=Regulatory` → allowed, but **no expiration block ever** |
| `time_shift` | ASG with scheduled scale-up/down in a region with `live`/`snapshot` grid data | `start_cron` ∈ window starts within `allowed_window` that fit the job duration | lowest mean-intensity window from the 7-day snapshot | none beyond standard tags |

Advisory-only (never a PR): `region_shift` (data residency is a human decision), `decommission`
(deleting resources is a human decision), anything below `min_saving_kg_co2e_yr`.

The same templates produce the gate's suggestions on pull requests (`docs/GATE.md`): rendered onto the
PR's head, validated with `tofu plan`, posted with their own carbon delta.

## rightsize

```hcl
# before                                   # after
resource "aws_db_instance" "reporting" {   resource "aws_db_instance" "reporting" {
  instance_class = "db.r5.4xlarge"           instance_class = "db.r5.xlarge"
  ...                                        ...
}                                          }
```

For ASGs the attribute is `instance_type` in the `aws_launch_template`.

## schedule

Adds two `aws_autoscaling_schedule` resources next to the ASG. Never edits the ASG's own size.

```hcl
resource "aws_autoscaling_schedule" "gpu_inference_off" {
  scheduled_action_name  = "emissiongate-off"
  autoscaling_group_name = aws_autoscaling_group.gpu_inference.name
  recurrence             = "0 20 * * MON-FRI"
  time_zone              = "America/New_York"
  min_size               = 0
  max_size               = 0
  desired_capacity       = 0
}

resource "aws_autoscaling_schedule" "gpu_inference_on" {
  scheduled_action_name  = "emissiongate-on"
  autoscaling_group_name = aws_autoscaling_group.gpu_inference.name
  recurrence             = "0 8 * * MON-FRI"
  time_zone              = "America/New_York"
  min_size               = 4
  max_size               = 4
  desired_capacity       = 4
}
```

PR body must state the cold-start implication for the first request after 08:00.

## graviton

Changes `instance_type` and `image_id` in the launch template. The AMI is a variable
(`var.ami_arm64`) in the estate, so the diff is two lines.

```hcl
resource "aws_launch_template" "legacy_worker" {
  instance_type = "m7g.2xlarge"        # was m5.2xlarge
  image_id      = var.ami_arm64        # was var.ami_x86_64
}
```

## storage_tier

Adds a lifecycle configuration with a transition only.

```hcl
resource "aws_s3_bucket_lifecycle_configuration" "compliance_logs" {
  bucket = aws_s3_bucket.compliance_logs.id
  rule {
    id     = "emissiongate-tier"
    status = "Enabled"
    filter {}
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
    # no expiration block — ever, for Retention=Regulatory
  }
}
```

Under the methodology this saves ≈ 0 kgCO2e, so it normally lands as `below_threshold` advisory. That
is intended; see METHODOLOGY §3.

## time_shift

Moves the recurrence of an existing scheduled scale-up/scale-down pair.

```hcl
resource "aws_autoscaling_schedule" "nightly_etl_up" {
  recurrence = "30 3 * * *"     # was "0 2 * * *"
  time_zone  = "Europe/London"
}
resource "aws_autoscaling_schedule" "nightly_etl_down" {
  recurrence = "30 5 * * *"     # was "0 4 * * *"
  time_zone  = "Europe/London"
}
```

The PR body shows the 7-day mean intensity for the old and new windows and tonight's forecast, each
with its tier.

## Adding a template

Use the `/add-intervention` skill. It updates, in one change: `Intervention` literal in
`contracts.py` and DATA_CONTRACTS.md, a module in `core/patches/`, the registry, `policy.yaml`
compatibility, the savings function with a golden test, a `tofu`-marked render test, and this file.
