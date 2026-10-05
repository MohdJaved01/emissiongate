# ADR-0011: GitHub via httpx REST, not PyGithub

- Status: accepted
- Date: 2026-09-28

## Context

PyGithub is LGPL-3.0. Live mode needs about five endpoints.

## Decision

Call the GitHub REST API with httpx. Token scopes: contents write and pull requests write on the estate repo only.

## Consequences

No copyleft dependency; fully mockable with respx.
