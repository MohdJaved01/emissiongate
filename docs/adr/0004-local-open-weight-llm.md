# ADR-0004: Local open-weight LLM via Ollama (Qwen, Apache-2.0)

- Status: superseded by ADR-0013 for the model choice; the licence exclusions (Llama, Codestral) still apply
- Date: 2026-09-28

## Context

The organisers require an open-source LLM. The agent's energy must be reported; hosted inference energy is not measurable and published estimates vary by more than 10x.

## Decision

Serve models locally with Ollama. Defaults: `qwen3.5:9b` (small tier: planning, classification, narrative) and `qwen3.6:27b-coding` (large tier: patch decision, repair). Both Apache-2.0. Llama (community licence) and Codestral (non-production licence) are excluded. A hosted OpenAI-compatible fallback exists but is off by default and marks SCI incomplete.

## Consequences

Inference energy is inside the codecarbon measurement, so E is measured, not assumed. No data leaves the machine. Runs are slower; the demo shows real time. Low-RAM machines can use the small model for both tiers.
