# AGENTS.md — src/emissiongate/core

Applies to everything under `core/`. The root `AGENTS.md` still applies; this file adds to it.

- Pure functions over typed inputs. No network, no subprocess, no clock reads except through an injected
  parameter, no randomness except through an injected seeded generator.
- Allowed imports: standard library, `pydantic`, `yaml`, and `emissiongate.contracts`. Nothing else.
- Every coefficient comes through `core/factors.py`, which returns the value **and** a `Provenance`.
  Unknown instance type, processor or region raises `FactorNotFound`; never substitute a default.
- Units in every name (`kwh_yr`, `g_per_kwh`, `watts`). Keep floats unrounded; rounding happens in `report/`.
- Golden values in `docs/METHODOLOGY.md §6` are the contract. A change that moves a golden value needs a
  methodology change, a new ADR and the `methodology_auditor` review — not a test edit.
- `core/patches/` renderers return complete new file contents from a template and validated parameters.
  They never accept free-form HCL from anywhere.
- `core/ledger.py` is INSERT-only; a trigger rejects UPDATE and DELETE. A failed write raises.

## Code Review Rules

- **Methodology drift (P0).** Flag any change to formulas in `energy.py`, `grid.py`, `sci.py` or savings
  functions that is not mirrored in `docs/METHODOLOGY.md`. Safe path: update the methodology and golden
  tests in the same change, with an ADR.
- **Hidden defaults (P0).** Flag `dict.get(..., <number>)`, `or <number>` or similar fallbacks on factor,
  intensity or price lookups. Safe path: raise, or fall back to a documented tier with provenance.
- **Impurity (P1).** Flag I/O, logging of payloads, global state or non-injected randomness/clock in `core/`.
- **Guardrail defaults (P0).** Flag policy code that returns "allowed" when a tag, policy key or
  suppression file is missing or unparseable.
- **Renderer scope (P1).** Flag renderers that touch resources other than the candidate's own file or that
  can emit `expiration`, deletion or resource removal.
