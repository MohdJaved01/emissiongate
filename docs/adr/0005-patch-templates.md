# ADR-0005: Patch templates with parameters, not free-form HCL

- Status: accepted
- Date: 2026-09-28

## Context

A 9-27B local model writes plausible but often invalid HCL. Each failed plan costs a repair loop, energy and demo time.

## Decision

The model selects a template and parameter values from allowed lists (`PatchDecision`). `core/patches` renders the HCL deterministically.

## Consequences

Higher first-attempt plan success, fewer tokens, a cleaner trust boundary. Adding a new kind of fix means writing a template, which is deliberate friction.
