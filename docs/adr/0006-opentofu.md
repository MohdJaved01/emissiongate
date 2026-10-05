# ADR-0006: OpenTofu instead of Terraform CLI

- Status: accepted
- Date: 2026-09-28

## Context

Terraform 1.6+ is under the Business Source License (now held by IBM), which is not open source. The project claims an all-open-source toolchain.

## Decision

Use OpenTofu (MPL-2.0) for fmt/validate/plan. The estate is written in the Terraform language, which OpenTofu reads unchanged.

## Consequences

The open-source claim holds. The binary is `tofu`; configurable via `EG_TOFU_BIN`.
