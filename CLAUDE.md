# CLAUDE.md — EmissionGate

The canonical instructions live in `AGENTS.md`, shared with Codex. Claude Code loads them here:

@AGENTS.md

## Claude Code specifics

- **Nested rules.** Claude Code does not auto-load `AGENTS.md` files in subdirectories. Before editing
  anything under `src/emissiongate/core/` or `src/emissiongate/llm/`, read the `AGENTS.md` in that folder.
- **Skills.** `.claude/skills/*` are thin pointers to the canonical skills in `.agents/skills/*`. Invoke
  them as `/milestone M3`, `/check-invariants`, `/add-intervention <name>`, `/score-run`, `/model-bakeoff`.
  Edit the canonical file, never the pointer.
- **Subagents.** `.claude/agents/*` point at `docs/review/*.md`, shared with Codex's `.codex/agents/*.toml`.
- **Permissions.** `.claude/settings.json` denies `tofu apply|destroy`, `terraform`, the AWS CLI,
  `make demo-live`, and reading `.env`. The Codex equivalents are in `.codex/rules/` and `.codex/config.toml`.
- Run `make agent-check` after touching `AGENTS.md`, `.agents/`, `.codex/` or `.claude/`.
