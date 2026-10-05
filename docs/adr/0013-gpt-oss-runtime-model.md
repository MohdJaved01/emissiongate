# ADR-0013: Runtime model — gpt-oss-20b, one resident model with two reasoning levels

- Status: accepted, pending bake-off outcome
- Date: 2026-09-30
- Supersedes: ADR-0004 (model choice only; its licence exclusions still apply)

## Context

The organisers require an open-source LLM, and the project is also entered in an OpenAI Codex hackathon.
ADR-0004 chose two dense Qwen models (9B and 27B coding). Since ADR-0005 the model no longer writes code,
so a coding-specialised model no longer earns its memory. Two dense models on a laptop mean roughly 24 GB
resident, or swapping models between calls, which costs time and energy.

`gpt-oss-20b` is OpenAI's open-weight model under Apache-2.0: a mixture-of-experts with about 21B total and
3.6B active parameters per token, a 128K context, about 14 GB in Ollama, and adjustable reasoning
(`think`: low | medium | high).

## Decision

The default runtime model is `gpt-oss:20b`, kept resident for both tiers:

- `EG_THINK_SMALL=low` — scan planning, ambiguous classification, PR narrative
- `EG_THINK_LARGE=medium` — patch decision, parameter repair

`qwen3.5:9b` and `qwen3.6:27b-coding` remain configured alternatives. The choice is confirmed or reversed by
the bake-off (BUILD_PLAN M1.5) using one rule: among models with **≥ 95 % schema-valid responses on the
first try** and **≥ 90 % decision agreement** on `fixtures/llm_cases`, choose the lowest measured energy per
case. If no model qualifies, offline behaviour stays the default.

## Consequences

- Fits 16 GB machines; one model resident; no swapping between tiers.
- Fewer active parameters per token should mean less energy per token, but gpt-oss always spends some
  thinking tokens, so net energy is **measured**, never assumed.
- Known risk: structured-output enforcement for gpt-oss in Ollama has had open bugs, notably with streaming
  plus thinking on the OpenAI-compatible endpoint. Mitigations: non-streaming native `/api/chat`, fence
  stripping, pydantic validation, one re-ask, deterministic fallback — and the bake-off gate.
- One model satisfies both an "open-source LLM" rule and an OpenAI-hosted hackathon.
- Developers may also run Codex itself on the same local model (`codex --oss`); optional, see
  `docs/DEVELOPING.md`.

## Outcome

_Pending M1.5. Append the bake-off table and the resulting choice here — do not edit the decision above._

## Amendment — 5 Oct 2026

- **Correction.** "Fits 16 GB machines" above is wrong for ordinary laptops. OpenAI's guidance for
  `gpt-oss-20b` is at least 16 GB of GPU or unified memory. On a 16 GB-RAM laptop without a GPU it does not
  fit beside the operating system. Development and the demo use a 32 GB machine (CPU inference under WSL2
  with 20 GB assigned).
- **Bake-off not run for the submission.** `gpt-oss:20b` is the default without the measured comparison
  in M1.5; the README lists the bake-off as designed, not built. Smaller local options for 16 GB machines
  (`qwen3.5:4b`, about 3.3 GB) remain configurable through `.env`.
