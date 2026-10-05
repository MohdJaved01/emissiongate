# ADR-0016: Claude Code builds the submission; the repository stays Codex-ready

- Status: accepted
- Date: 2026-10-05
- Amends: ADR-0012 (primary development tool only; `AGENTS.md` stays canonical)

## Context

ADR-0012 made Codex the primary development tool. Codex licences were provided late in the hackathon
window (on <DATE LICENCES ARRIVED>). Codex built and verified an M0 scaffold on a Windows work laptop on
4–5 October, but that machine had no Linux toolchain for the Makefile and 16 GB of RAM, too little for
the local `gpt-oss-20b` model (ADR-0013 amendment). The submission was due on 5 October.

## Decision

- The submission is built from scratch with **Claude Code** on a 32 GB machine under WSL2, with the
  Claude Code sandbox on and network-dependent steps run by the human.
- The Codex M0 prototype is not carried into this repository; the repository history starts from the
  design kit.
- `AGENTS.md` remains the canonical instruction file, and `.codex/` (sandbox, command rules, skills,
  reviewers) is kept, so Codex can continue the work without changes.
- `docs/augmentation-log.md` records exactly which tool did what, including Codex's limited role.

## Consequences

- One coding agent for the whole build: fewer handovers on the deadline day.
- The commands judges run (`make …` on Linux) are the commands that were tested during the build.
- Codex usage in this submission is limited to the M0 prototype and, if time allows, read-only reviews;
  the augmentation log says so rather than overstating it.
