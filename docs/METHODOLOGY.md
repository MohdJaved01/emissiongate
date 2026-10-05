# Methodology

How EmissionGate turns usage into kWh and kgCO2e, how it values each intervention, and how it
measures its own footprint. Every coefficient here comes from `factors/ccf_aws_f584c54.json`, which is
extracted by script from Cloud Carbon Footprint (Apache-2.0) at commit
`f584c549ee358d5980d36513267d007ecd3ee716`. Do not type coefficients into code — load them.

Scope: operational (use-phase) Scope 2 emissions of cloud resources, **location-based** per the GHG
Protocol Scope 2 Guidance. Embodied hardware emissions of cloud resources are out of scope for v1.

## 1. Energy per resource

For a resource over `hours` with average CPU utilisation `u_cpu` and GPU utilisation `u_gpu` (0..1):

```
cpu_watts    = vcpu × (min_w_cpu + u_cpu × (max_w_cpu − min_w_cpu))        # watts per vCPU, CCF
gpu_watts    = gpu_count × (min_w_gpu + u_gpu × (max_w_gpu − min_w_gpu))   # watts per GPU, CCF
mem_watts    = max(0, memory_gib − 4 × vcpu) × memory_kwh_per_gb_hour × 1000   # EG-simplification-1
it_watts     = cpu_watts + gpu_watts + mem_watts
wall_watts   = it_watts × pue                                            # pue = 1.135
kwh          = wall_watts × hours / 1000

storage_kwh  = tb × coef_wh_per_tb_hour × replication × pue × hours / 1000  # ssd 1.2, hdd 0.65
network_kwh  = gb_transferred × 0.001 × pue
```

When an instance maps to several processors (e.g. Cascade Lake + Skylake), average their min and max
watts, as CCF does.

Annualisation: `kwh_yr = kwh_window × 8760 / window_hours` for steady patterns. For patterns with a
schedule, use the observed hourly activity mask over the look-back window (35 days).

## 2. Emissions

```
kg_co2e = kwh × g_per_kwh / 1000
```

Grid intensity has three tiers. The tier used is stamped on every figure.

| Tier | Source | Resolution | Coverage | Used for |
|---|---|---|---|---|
| `live` | UK Carbon Intensity API (regional, London) | half-hourly, 48h forecast | `eu-west-2` only | choosing tonight's time-shift window |
| `snapshot` | `fixtures/grid/uk_london_*.json` (7 days history + 48h forecast) | half-hourly | `eu-west-2` only | time-shift savings; offline fallback for `live` |
| `annual` | CCF region factor in the vendored factors file | annual | all AWS regions | **all annual resource totals** |

Decision (ADR-0007): annual resource totals use the `annual` tier everywhere, so regions are compared on
one basis. Half-hourly data is used where it changes a decision — when to run deferrable work.

Examples from the vendored file (g/kWh): us-east-1 365.128 (NERC SERC), us-west-2 298.650 (WECC),
eu-west-1 305.0, eu-west-2 305.0, eu-north-1 8.0, ap-south-1 951.82.

## 3. Savings per intervention

All savings are annual, location-based, and computed in `core/`. Cost savings use synthetic list prices
from the estate generator and are labelled synthetic.

| Template | kWh saving | Notes |
|---|---|---|
| `rightsize` | `kwh(old, u) − kwh(new, u × vcpu_old / vcpu_new)` | new utilisation capped at 1.0; rejected if new p95 > `rightsize_target_p95_max` |
| `schedule` | energy of off-hours removed | off-hours = hours outside the observed activity mask; assumes scaled to zero |
| `graviton` | `kwh(x86, u) − kwh(arm, u)` | EG-simplification-2: equal work per vCPU; arm64 build effort not modelled, stated in PR |
| `storage_tier` | `kwh(class_old) − kwh(class_new)` | under CCF both S3 Standard and archive classes use the HDD coefficient → **≈ 0 kWh** |
| `time_shift` | kWh unchanged; `kg = kwh_job × (I_now − I_new)` | only where `live`/`snapshot` data exists; ΔI from the 7-day mean per half-hour slot, not one night's forecast |

`storage_tier` is deliberately kept honest: it is a large cost saving and, under this methodology, almost
no carbon saving. It is the clearest demonstration that ranking by carbon and ranking by cost disagree.
Do not tune coefficients to make it look better.

EG-simplification-3: rightsizing across GPU types keeps GPU utilisation unchanged, which overstates the
saving (a smaller GPU runs hotter). Such candidates are marked `confidence: low`.

## 3b. Projection for proposed changes (PR gate)

The gate compares two configurations, so for some resources there is no utilisation yet.

| Case | Utilisation used | Label |
|---|---|---|
| existing resource with telemetry, unchanged shape | observed (35-day window) | `observed` |
| capacity change | `u_new = min(1, u_old × count_old / count_new)` — total work held constant | `observed, projected` |
| instance type change | `u_new = min(1, u_old × vcpu_old / vcpu_new)` | `observed, projected` |
| new resource, no telemetry | CPU `default_cpu_utilization` = 0.50 (CCF's `AVG_CPU_UTILIZATION_2020`); GPU 0.50 (no published default); band 0.10–0.90 | `assumed` |
| removed resource | current observed energy, as a negative delta | `observed` |

Hours come from `aws_autoscaling_schedule` recurrences (24×7 when none). Totals use the annual tier, like
the sweep. Assumed figures are always published as central value plus range, never as a bare number.
After merge, the sweep compares the prediction with observed values (GATE §7).

## 4. Reconciliation

The run compares the bottom-up monthly total with a CCFT-shaped monthly total and reports the variance
per region. **In this synthetic project the CCFT totals are generated with a seeded bias** to exercise the
code path; they are not an independent check. With real data, CCFT Data Exports provide the independent,
audited total. The report must say this in the reconciliation section.

## 5. The agent's own footprint (SCI)

```
SCI = (E × I + M) / R           ISO/IEC 21031:2024
```

| Term | How | Label in report |
|---|---|---|
| E | `codecarbon.EmissionsTracker(tracking_mode="machine")` wraps the run; covers the Ollama process on the same machine | `measured` if RAPL / powermetrics / NVML; `estimated` if TDP fallback |
| I | codecarbon's grid intensity for the machine's country; CCF `ap-south-1` shown as a cross-check when in India | sourced |
| M | `EG_DEVICE_EMBODIED_KG_CO2E × run_seconds / (EG_DEVICE_LIFESPAN_YEARS × 31_536_000)` | `not declared` when unset — never defaulted |
| R | one estate scan; also per accepted recommendation | counted |

Also reported: **payback ratio** = annual kgCO2e avoided by merged PRs ÷ kgCO2e per run (and the same
with proposed PRs, labelled as such); **marginal LLM energy** = E(local mode) − E(offline mode) for the
same seed; tokens by model, cache hits, LLM calls, tool calls, repair attempts, first-attempt plan
success rate.

If the hosted fallback LLM is used, E no longer includes inference; the report must say "inference
energy not measured" and SCI is incomplete.

## 6. Golden values (tests must match to 3 decimal places)

Computed from `factors/ccf_aws_f584c54.json` with the formulas above.

Savings and deltas are differences of the published before/after values, each rounded to 3
decimals. The unrounded difference can differ by up to 0.001 (G2 36.4384, G3 96.6246, G6 +59.1945 and
−232.2165); reports publish the difference of the rounded values; tests check
both (clarified 5 Oct 2026 in M3; no formula changed).

**G1 — idle GPU inference instance.** `g5.2xlarge` (8 vCPU AMD EPYC 2nd Gen, 1× Nvidia A10G, 32 GiB),
u_cpu 0.05, u_gpu 0.04, us-east-1, 8760 h.
`it_watts 27.648`, `wall_watts 31.3805`, `kwh 274.893`, `kg_co2e 100.371`.
Scheduled to 60 h/week: `kwh 98.176`, `kg 35.847` → saving **64.524 kgCO2e/yr per instance**.

**G2 — Graviton migration.** `m5.2xlarge` (8 vCPU Skylake) at u 0.60, eu-west-1:
`it 21.632`, `wall 24.5523`, `kwh 215.078`, `kg 65.599`.
`m7g.2xlarge` (8 vCPU Graviton3) at u 0.60: `it 9.616`, `wall 10.9142`, `kwh 95.608`, `kg 29.160`.
Saving **36.439 kgCO2e/yr per instance**.

**G3 — database rightsize.** `db.r5.4xlarge` (16 vCPU, 128 GiB) at u 0.05, us-east-1:
`it 38.232` (of which memory 25.088), `wall 43.3933`, `kwh 380.125`, `kg 138.794`.
`db.r5.xlarge` (4 vCPU, 32 GiB) at u 0.20: `it 11.616`, `wall 13.1842`, `kwh 115.493`, `kg 42.170`.
Saving **96.624 kgCO2e/yr**.

**G4 — storage.** 8 × 0.5 TB orphaned EBS (SSD, replication 2), us-east-1: `kwh 95.449/yr`, `kg 34.851/yr`.
40 TB S3 Standard (HDD, replication 6), eu-west-2 annual: `kwh 1551.046/yr`, `kg 473.069/yr`;
tiering to an archive class: **≈ 0 kg saving** under this methodology.

**G5 — gate, new GPU fleet (assumed).** 2 × `g5.2xlarge`, us-east-1, 24×7, CPU = GPU utilisation:
0.10 → `kwh 720.560`, `kg 263.097`; 0.50 → `kwh 1871.993`, `kg 683.517`; 0.90 → `kwh 3023.425`, `kg 1103.937`.

**G6 — gate, scale-out (observed, projected).** `m5.2xlarge` 6 → 10, eu-west-1, u 0.60 → 0.36:
base `kwh 1290.470`, `kg 393.593`; head `kwh 1484.549`, `kg 452.788`; delta **+59.195**. Suggested
`m7g.2xlarge` × 10 at u 0.36: `kwh 723.185`, `kg 220.571` → **−232.217** vs head.

**G7 — gate, region move (observed).** 4 × `c5.2xlarge` at u 0.80 for 730 h/yr: eu-west-2 `kwh 89.987`,
`kg 27.446` → eu-north-1 `kg 0.720`; delta **−26.726**.

### Scale check

Per-resource figures are tens to low hundreds of kgCO2e per year. That is what the published
coefficients say, and the project reports it as it is. Present totals per estate and "per 1,000
resources" in the pitch; never inflate a per-resource figure.

## 7. Declared simplifications

- **EG-simplification-1** — memory energy counted only above 4 GiB per vCPU, as a proxy for memory not
  already inside SPECpower-derived per-vCPU watts. CCF uses a more detailed per-processor baseline
  (`MEMORY_BY_COMPUTE_PROCESSOR`, vendored but unused in v1).
- **EG-simplification-2** — Graviton migration assumes equal work per vCPU.
- **EG-simplification-3** — cross-GPU-type rightsizing keeps GPU utilisation unchanged.
- Hourly averages hide sub-hour peaks. Multi-AZ standby compute is not modelled. Embodied carbon of cloud
  hardware is excluded.
