## Schedule gpu-inference to its weekly activity window (−258.1 kgCO2e/yr)

> **Synthetic estate — all data is synthetic.** Drafted by EmissionGate (`local` run `20261005T091433Z-local-s42`).
> Nothing has been applied: EmissionGate cannot apply, merge or delete. A human decides.

| | Before | After | Change |
|---|---:|---:|---:|
| **kgCO2e / year** | 401.5 | 143.4 | **−258.1** |
| kWh / year | | | −706.9 |
| Cost / year (synthetic USD) | | | −27,301 |

**What changes.** Adds two `aws_autoscaling_schedule` resources next to the group: scale to 0 at `0 20 * * MON-FRI` and back to 4 at `0 8 * * MON-FRI` (America/New_York). The group's own size is unchanged.

**Why.** This change aligns GPU inference usage with business hours, reducing idle capacity and improving cost efficiency. The reviewer should verify that the cron schedules are correct for the target time zone and that the scaling logic handles cold starts gracefully.

**Evidence** (35-day window, 840 hourly datapoints)
- CPU average 5%, p95 6%; GPU average 4%
- Active 36% of hours; weekly regularity 100%; activity inside the weekly mask 100%
- Resource: `aws_autoscaling_group.gpu_inference` in `gpu_inference.tf`, us-east-1, 4 × g5.2xlarge
- Tags: `Environment=staging`, `Owner=ml-platform`

**Assumptions and risks** (confidence: high)
- On 60 h/week; scaled to zero outside the schedule.
- Cold start: the first request after scale-up waits for instances to boot.
- Potential service latency during cold starts may affect user experience.
- Incorrect cron syntax could lead to unintended scaling windows.
- Time zone misconfiguration might cause off‑peak usage to persist.

**Validation.** `tofu fmt -check`, `tofu validate` and `tofu plan -refresh=false` passed on attempt 1 (offline, providers from the local mirror, dummy credentials — plans never contact AWS).

**Provenance**
- `ccf@f584c54` version `f584c549ee35`, tier `vendored`
- `ccf@f584c54` version `f584c549ee35`, tier `annual`
- Ledger events: quantified #19, valued #43, validated #42 (`runs/20261005T091433Z-local-s42/ledger.sqlite`)

```diff
--- a/gpu_inference.tf
+++ b/gpu_inference.tf
@@ -33,3 +33,25 @@
     propagate_at_launch = true
   }
 }
+
+resource "aws_autoscaling_schedule" "gpu_inference_off" {
+  provider               = aws.us_east_1
+  scheduled_action_name  = "emissiongate-off"
+  autoscaling_group_name = aws_autoscaling_group.gpu_inference.name
+  recurrence             = "0 20 * * MON-FRI"
+  time_zone              = "America/New_York"
+  min_size               = 0
+  max_size               = 0
+  desired_capacity       = 0
+}
+
+resource "aws_autoscaling_schedule" "gpu_inference_on" {
+  provider               = aws.us_east_1
+  scheduled_action_name  = "emissiongate-on"
+  autoscaling_group_name = aws_autoscaling_group.gpu_inference.name
+  recurrence             = "0 8 * * MON-FRI"
+  time_zone              = "America/New_York"
+  min_size               = 4
+  max_size               = 4
+  desired_capacity       = 4
+}
```

<sub>Figures come from EmissionGate's deterministic core (docs/METHODOLOGY.md, Cloud Carbon Footprint coefficients at commit f584c54). The "Why" paragraph is prose only (written by a local open-weight model; numbers are never taken from it). Annual, location-based Scope 2 estimates, not meter readings.</sub>
