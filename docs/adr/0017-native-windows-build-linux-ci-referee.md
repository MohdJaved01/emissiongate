# ADR-0017: Build on native Windows; Linux CI is the referee

- Status: accepted
- Date: 2026-10-05
- Amends: ADR-0016 (build environment only)

## Context

ADR-0016 says the submission is built with Claude Code on a 32 GB machine under WSL2. On build day the
machine (Windows 11, 32 GB RAM, Intel Core Ultra 9) had no WSL distribution installed, no `make`, and
the repository sat in a OneDrive-synced folder with spaces in its path. Installing WSL2 needs a reboot and
setup time the deadline did not allow.

## Decision

- Claude Code (VS Code extension) builds the submission on **native Windows**. The working copy was
  moved to `C:\dev\emissiongate`, outside OneDrive, so sync locks cannot touch git or the SQLite ledger.
- The human approved installing the toolchain from official sources: Python dependencies from PyPI
  (`uv`), OpenTofu 1.13 (`winget OpenTofu.Tofu`), Ollama (`winget Ollama.Ollama`), and the AWS provider
  mirror (`tofu providers mirror`, signed packages, `windows_amd64` and `linux_amd64`).
- All code is cross-platform (no shell-specific paths; `tofu` is called with argument lists).
- **GitHub Actions on `ubuntu-latest` is the acceptance referee**: it runs the real `make` targets
  (`setup agent-check providers lint test demo-offline score`), which is what judges run.

## Consequences

- Local commands use `.venv\Scripts\...` equivalents of the Makefile targets; the Makefile is unchanged.
- A milestone is "done" when it is green locally and in Linux CI.
- The augmentation log names the real environment, not the planned one.
