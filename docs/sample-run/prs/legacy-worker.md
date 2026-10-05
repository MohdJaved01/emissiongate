## Move legacy-worker to Graviton m7g.2xlarge (−218.6 kgCO2e/yr)

> **Synthetic estate — all data is synthetic.** Drafted by EmissionGate (`local` run `20261005T091433Z-local-s42`).
> Nothing has been applied: EmissionGate cannot apply, merge or delete. A human decides.

| | Before | After | Change |
|---|---:|---:|---:|
| **kgCO2e / year** | 393.6 | 175.0 | **−218.6** |
| kWh / year | | | −716.8 |
| Cost / year (synthetic USD) | | | −3,027 |

**What changes.** Moves the launch template from `m5.2xlarge` to `m7g.2xlarge` and the image to `var.ami_arm64` (two lines).

**Why.** This change replaces legacy-worker instances with Graviton-based m7g.2xlarge, improving performance and reducing carbon emissions while maintaining equivalent workload capacity. The reviewer should verify that the arm64 build is compatible and that the new instance type meets all operational requirements.

**Evidence** (35-day window, 840 hourly datapoints)
- CPU average 60%, p95 65%
- Active 100% of hours; weekly regularity 100%; activity inside the weekly mask 100%
- Resource: `aws_autoscaling_group.legacy_worker` in `legacy_worker.tf`, eu-west-1, 6 × m5.2xlarge
- Tags: `Environment=prod`, `Owner=data`

**Assumptions and risks** (confidence: medium)
- Equal work per vCPU assumed (EG-simplification-2).
- Requires an arm64 build of the workload.
- Potential incompatibility of the arm64 build with existing dependencies
- Uncertain impact on performance under peak load
- Need to confirm that the new instance type aligns with current cost and scaling policies

**Validation.** `tofu fmt -check`, `tofu validate` and `tofu plan -refresh=false` passed on attempt 1 (offline, providers from the local mirror, dummy credentials — plans never contact AWS).

**Provenance**
- `ccf@f584c54` version `f584c549ee35`, tier `vendored`
- `ccf@f584c54` version `f584c549ee35`, tier `annual`
- Ledger events: quantified #20, valued #50, validated #49 (`runs/20261005T091433Z-local-s42/ledger.sqlite`)

```diff
--- a/legacy_worker.tf
+++ b/legacy_worker.tf
@@ -4,8 +4,8 @@
 resource "aws_launch_template" "legacy_worker" {
   provider      = aws.eu_west_1
   name          = "eg-legacy-worker"
-  image_id      = var.ami_x86_64
-  instance_type = "m5.2xlarge"
+  image_id      = var.ami_arm64
+  instance_type = "m7g.2xlarge"
 }
 
 resource "aws_autoscaling_group" "legacy_worker" {
```

<sub>Figures come from EmissionGate's deterministic core (docs/METHODOLOGY.md, Cloud Carbon Footprint coefficients at commit f584c54). The "Why" paragraph is prose only (written by a local open-weight model; numbers are never taken from it). Annual, location-based Scope 2 estimates, not meter readings.</sub>
