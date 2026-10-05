---
name: score-run
description: Run the offline EmissionGate pipeline on seed 42 and report precision, recall, trap violations, carbon-vs-cost ranking and footprint. Use after any change that could affect outcomes.
---

# Score a run

1. Run `make estate demo-offline score`. This needs no network. If `tofu init` complains about missing
   providers, ask the human to run `make providers` once, then retry.
2. Read `runs/<latest>/score.json` and `runs/<latest>/manifest.json`.
3. Report briefly:
   - precision, recall and trap violations (must be zero) against `docs/SYNTHETIC_ESTATE.md §4`
   - the carbon rank order and the cost rank order side by side
   - annual kgCO2e avoided (proposed), coverage, advisories, escalations
   - energy per run and its label — sandboxed runs are **not** the measured figure; say so
4. If anything regressed against the README results table, say which change likely caused it. Never edit
   thresholds or golden values to make a run pass.
