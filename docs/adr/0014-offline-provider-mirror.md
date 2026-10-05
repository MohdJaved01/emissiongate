# ADR-0014: Offline OpenTofu provider mirror

- Status: accepted
- Date: 2026-09-30

## Context

The Validator runs `tofu plan` in a temporary copy of the estate for every candidate. Without a mirror,
each copy's `tofu init` downloads the AWS provider — a large binary — from the registry. That breaks
invariant 10 (offline mode needs no network), repeats a download per candidate (time and energy), and
fails inside the Codex sandbox and the agent phase of Codex cloud, where network is off by default.

## Decision

`make providers` mirrors the providers declared in `tofu/versions.tf` (OpenTofu ≥ 1.8, `hashicorp/aws ~> 6.0`)
into `.tofu-providers/` once per machine. `tools/tf.py` runs `tofu init -input=false -plugin-dir=$EG_TOFU_PLUGIN_DIR`
in every temporary copy. The estate generator copies `tofu/versions.tf` into the estate so both use the
same constraint.

## Consequences

Runs never touch the network. One download per machine instead of one per candidate. The mirror is
platform-specific (add `-platform=OS_ARCH` to mirror for other machines) and gitignored. A missing mirror
is a clear error that tells the human to run `make providers`.
