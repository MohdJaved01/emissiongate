## Schedule dev-api to its weekly activity window (−34.7 kgCO2e/yr)

> **Synthetic estate — all data is synthetic.** Drafted by EmissionGate (`local` run `20261005T091433Z-local-s42`).
> Nothing has been applied: EmissionGate cannot apply, merge or delete. A human decides.

| | Before | After | Change |
|---|---:|---:|---:|
| **kgCO2e / year** | 70.6 | 35.9 | **−34.7** |
| kWh / year | | | −113.9 |
| Cost / year (synthetic USD) | | | −7,088 |

**What changes.** Adds two `aws_autoscaling_schedule` resources next to the group: scale to 0 at `0 19 * * MON-FRI` and back to 12 at `0 9 * * MON-FRI` (Europe/London). The group's own size is unchanged.

**Why.** This change aligns the dev‑api schedule with typical business hours, reducing idle capacity while keeping the service available during peak periods. The reviewer should verify that the cron expressions correctly reflect the intended days and times and that the zero‑scale policy does not interfere with other dependent services.

**Evidence** (35-day window, 840 hourly datapoints)
- CPU average 10%, p95 34%
- Active 30% of hours; weekly regularity 100%; activity inside the weekly mask 100%
- Resource: `aws_autoscaling_group.dev_api` in `dev_api.tf`, eu-west-2, 12 × m5.large
- Tags: `Environment=dev`, `Owner=web`

**Assumptions and risks** (confidence: high)
- On 50 h/week; scaled to zero outside the schedule.
- Cold start: the first request after scale-up waits for instances to boot.
- Potential cold‑start latency for users after the service scales back up.
- Unintended impact on downstream services that expect continuous availability.
- Misconfiguration of the cron schedule could lead to unexpected downtime or resource usage.

**Validation.** `tofu fmt -check`, `tofu validate` and `tofu plan -refresh=false` passed on attempt 1 (offline, providers from the local mirror, dummy credentials — plans never contact AWS).

**Provenance**
- `ccf@f584c54` version `f584c549ee35`, tier `vendored`
- `ccf@f584c54` version `f584c549ee35`, tier `annual`
- Ledger events: quantified #17, valued #64, validated #63 (`runs/20261005T091433Z-local-s42/ledger.sqlite`)

```diff
--- a/dev_api.tf
+++ b/dev_api.tf
@@ -33,3 +33,25 @@
     propagate_at_launch = true
   }
 }
+
+resource "aws_autoscaling_schedule" "dev_api_off" {
+  provider               = aws.eu_west_2
+  scheduled_action_name  = "emissiongate-off"
+  autoscaling_group_name = aws_autoscaling_group.dev_api.name
+  recurrence             = "0 19 * * MON-FRI"
+  time_zone              = "Europe/London"
+  min_size               = 0
+  max_size               = 0
+  desired_capacity       = 0
+}
+
+resource "aws_autoscaling_schedule" "dev_api_on" {
+  provider               = aws.eu_west_2
+  scheduled_action_name  = "emissiongate-on"
+  autoscaling_group_name = aws_autoscaling_group.dev_api.name
+  recurrence             = "0 9 * * MON-FRI"
+  time_zone              = "Europe/London"
+  min_size               = 12
+  max_size               = 12
+  desired_capacity       = 12
+}
```

<sub>Figures come from EmissionGate's deterministic core (docs/METHODOLOGY.md, Cloud Carbon Footprint coefficients at commit f584c54). The "Why" paragraph is prose only (written by a local open-weight model; numbers are never taken from it). Annual, location-based Scope 2 estimates, not meter readings.</sub>
