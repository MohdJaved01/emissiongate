## Rightsize reporting-db: db.r5.4xlarge to db.r5.xlarge (−96.6 kgCO2e/yr)

> **Synthetic estate — all data is synthetic.** Drafted by EmissionGate (`local` run `20261005T091433Z-local-s42`).
> Nothing has been applied: EmissionGate cannot apply, merge or delete. A human decides.

| | Before | After | Change |
|---|---:|---:|---:|
| **kgCO2e / year** | 138.8 | 42.2 | **−96.6** |
| kWh / year | | | −264.6 |
| Cost / year (synthetic USD) | | | −13,140 |

**What changes.** Changes the instance size from `db.r5.4xlarge` to `db.r5.xlarge`.

**Why.** This change reduces the database instance size to better match current workload patterns, improving cost efficiency while maintaining performance. The reviewer should verify that the new instance type supports all required features and that monitoring alerts remain appropriate for the new configuration.

**Evidence** (35-day window, 840 hourly datapoints)
- CPU average 5%, p95 8%
- Active 0% of hours; weekly regularity 100%; activity inside the weekly mask n/a
- Resource: `aws_db_instance.reporting_db` in `reporting_db.tf`, us-east-1, 1 × db.r5.4xlarge
- Tags: `Environment=prod`, `Owner=finance`

**Assumptions and risks** (confidence: high)
- Potential performance impact if the workload increases unexpectedly
- Compatibility issues with existing extensions or plugins
- Risk of insufficient storage or I/O capacity for peak periods

**Validation.** `tofu fmt -check`, `tofu validate` and `tofu plan -refresh=false` passed on attempt 1 (offline, providers from the local mirror, dummy credentials — plans never contact AWS).

**Provenance**
- `ccf@f584c54` version `f584c549ee35`, tier `vendored`
- `ccf@f584c54` version `f584c549ee35`, tier `annual`
- Ledger events: quantified #25, valued #57, validated #56 (`runs/20261005T091433Z-local-s42/ledger.sqlite`)

```diff
--- a/reporting_db.tf
+++ b/reporting_db.tf
@@ -5,7 +5,7 @@
   provider                    = aws.us_east_1
   identifier                  = "eg-reporting-db"
   engine                      = "postgres"
-  instance_class              = "db.r5.4xlarge"
+  instance_class              = "db.r5.xlarge"
   allocated_storage           = 500
   username                    = "synthetic_admin"
   manage_master_user_password = true
```

<sub>Figures come from EmissionGate's deterministic core (docs/METHODOLOGY.md, Cloud Carbon Footprint coefficients at commit f584c54). The "Why" paragraph is prose only (written by a local open-weight model; numbers are never taken from it). Annual, location-based Scope 2 estimates, not meter readings.</sub>
