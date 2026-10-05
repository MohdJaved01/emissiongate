# Developing EmissionGate with Codex (and Claude Code)

Codex was planned as the primary development tool (ADR-0012); the submission itself was built with Claude Code
(ADR-0016). Both work from the same files. Both read the
same rules in `AGENTS.md`; tool-specific files only point at shared ones.

## 1. One-time setup — you, in your own terminal

```bash
git clone <your fork>/emissiongate && cd emissiongate
make setup          # venv, dependencies, .env from .env.example
make providers      # OpenTofu provider mirror (ADR-0014) — the last networked step for runs
make models         # ollama pull gpt-oss:20b (about 14 GB) — skip if you only use offline mode
codex               # first launch: mark the project as TRUSTED, or .codex/ is ignored
```

Inside Codex, run `/status` and check that the project config is loaded, then `/skills` and check you
see `milestone`, `check-invariants`, `add-intervention`, `score-run` and `model-bakeoff`.

Test the command rules without starting a session:

```bash
codex execpolicy check --pretty --rules .codex/rules/emissiongate.rules -- tofu apply -auto-approve
# -> forbidden, with the justification
```

## 2. What Codex can and cannot do here

| | Inside the sandbox (default) | Needs your approval | Forbidden by rules |
|---|---|---|---|
| Edit `src/`, `tests/`, `docs/` | ✓ | | |
| `make test lint estate demo-offline score agent-check` | ✓ (no network needed) | | |
| `git commit` | | ✓ (`.git/` is read-only in the sandbox) | |
| Edit `.agents/`, `.codex/` | | ✓ (protected paths) | |
| `make setup providers models demo bakeoff grid-snapshot` | | ✓ — better: run them yourself | |
| `git push`, `git reset/clean/rebase` | | ✓ | |
| `tofu apply/destroy/import/state`, `terraform`, `aws`, `make demo-live` | | | ✓ |

Network is off in the sandbox (`.codex/config.toml`). That is deliberate: it keeps tests honest
(invariant 10) and means nothing Codex runs can reach a real cloud account. When a step needs network or
the local model server, `AGENTS.md` tells Codex to stop and ask you to run it.

Command rules are a development guardrail, not the safety mechanism. The guarantees are structural: no
apply path exists in the code (invariant 3), the sandbox has no network, and the estate uses dummy
credentials.

## 3. The build loop

```text
$milestone M3                  # Codex  (Claude Code: /milestone M3)
  → Codex reads BUILD_PLAN M3 and the docs it points to, shows a plan — you approve
  → tests first for core/, then code
  → make lint test
  → make codex-review (separate read-only review process) and fixes findings
  → ticks the box in BUILD_PLAN, proposes commits — you approve
```

Gate work: `make gate BASE=main` runs the PR check for your current branch and prints the comment it
would post — no network, no token. Use it as a pre-push check while building M6.5.

Useful prompts:

- `make codex-review` — the dependable cold review: `codex review` driven by `docs/review/invariant-reviewer.md`.
- "Spawn the invariant_reviewer agent on my uncommitted changes." — quicker, same instructions.
- "Spawn the methodology_auditor agent; I changed core/energy.py."
- `$score-run` after anything that could change outcomes.
- `$add-intervention` then name the template, when adding a new kind of fix.

Skills take no arguments in Codex. Put the input in the same message: `$milestone M3`.

Nested rules: `src/emissiongate/core/AGENTS.md` and `src/emissiongate/llm/AGENTS.md` load automatically
only when a Codex session starts inside that folder. `AGENTS.md` tells Codex to read them before editing
those packages; if you start Codex inside `src/emissiongate/core/`, they load directly.

## 4. Reviews — same rules everywhere

| Where | How | Reads |
|---|---|---|
| From the shell (primary) | `make codex-review` → `codex review -` with `docs/review/invariant-reviewer.md` as the instructions | that file + `AGENTS.md` |
| During a task | spawn `invariant_reviewer` / `methodology_auditor` | `docs/review/*.md` |
| Interactive | `/review` → "Review uncommitted changes" | `AGENTS.md` |
| On GitHub | comment `@codex review` (Codex GitHub app) | `## Code Review Rules` in the nearest `AGENTS.md` |
| On GitHub, API key | add label `codex-review` → `.github/workflows/codex-review.yml` | `.github/codex/invariant-review.md` |

Codex's GitHub review posts only P0/P1 findings, which is why the review rules are written as P0/P1.

## 5. Codex cloud

Configure in Settings → Codex Cloud → Environments:

- **Install script:** contents of `scripts/codex-cloud-install.sh` (Python 3.12, OpenTofu via its signed
  apt repository, provider mirror, agent-file check).
- **Internet:** "Package managers" preset plus `get.opentofu.org`, `packages.opentofu.org`,
  `registry.opentofu.org`, `github.com`, `objects.githubusercontent.com`.
- **Start skill:** "No services. Verify with `make agent-check test`."
- **Secrets:** none. Cloud tasks never need `GITHUB_TOKEN`.

Cloud VMs have no local model server and 8–16 GB of RAM, so cloud tasks are for code, tests and offline
mode. Model-dependent work (M7, the bake-off, `make demo`) happens on your laptop.

## 6. Things you run yourself, and why

| Command | Why not Codex |
|---|---|
| `make demo` | needs `localhost:11434`; the sandbox blocks loopback |
| **the measured demo run** | energy must be measured without an agent harness around it; sandboxed timings are not the SCI figure |
| `make bakeoff` | needs the local model server; picks the runtime model (ADR-0013) |
| `make demo-live` | opens real pull requests — a human decision |
| `make grid-snapshot` | network |

## 7. Secrets

Codex can read any file in the workspace, and the Codex config has no equivalent of Claude Code's
"deny reading `.env`". So `GITHUB_TOKEN` never goes in `.env`: export it in your own terminal only for
`make demo-live`, then close that terminal. The hosted-fallback key, if you ever use one, is treated the
same way (invariant 13).

## 8. Running Codex itself on a local model (optional)

`codex --oss -m gpt-oss:20b` runs the coding agent on the same open-weight model the product uses, fully
offline. It is useful for a "built with open weights end to end" story, but a 20B local model is a much
weaker coding agent than Codex's default cloud models. Use it for small tasks, not for building the
pipeline. Ollama recommends at least a 64k context window for Codex.

## 9. Claude Code ↔ Codex

| Purpose | Claude Code | Codex |
|---|---|---|
| Instructions | `CLAUDE.md` (imports `AGENTS.md`) | `AGENTS.md` |
| Nested instructions | read on demand (told to) | loaded root → working directory only |
| Skills | `.claude/skills/*` (pointers) · `/milestone M3` | `.agents/skills/*` (canonical) · `$milestone M3` |
| Skill arguments | `$ARGUMENTS` | none — put input in the message |
| User-only skills | `disable-model-invocation: true` | description says "use only when the user names…"; implicit invocation left on so `$name` always resolves |
| Reviewers | `.claude/agents/*.md` (auto-delegated) | `.codex/agents/*.toml` (spawn on request) |
| Command permissions | `.claude/settings.json` allow/deny | `.codex/rules/*.rules` allow/prompt/forbidden |
| Sandbox / network | settings-level | `.codex/config.toml` — workspace-write, network off |
| Deny reading `.env` | `Read(./.env)` | no equivalent → no secrets in files |
| PR review | — | `@codex review`, `/review`, `codex exec` |

After editing any of these files: `make agent-check`.

## 10. Troubleshooting

- **`.codex/` seems ignored** — the project is not trusted. Re-launch Codex and trust it; check `/status`.
- **A skill is missing** — skills live in `.agents/skills/<name>/SKILL.md` (not `.codex/skills`). Run
  `make agent-check`. If `$milestone` isn't recognised, pick it from `/skills`.
- **A reviewer agent ignores its definition** — an open Codex issue reports custom agents in
  `.codex/agents/` sometimes spawning with the parent's settings instead of their own. You'll notice
  because it doesn't cite `docs/review/…`. Use `make codex-review`, which doesn't depend on agent loading.
- **`tofu init` tries to download** — the mirror is missing or `-plugin-dir` isn't passed. Run
  `make providers` yourself.
- **Instructions look truncated** — root + nested `AGENTS.md` over 32 KiB. `make agent-check` reports it.
- **gpt-oss returns fenced or invalid JSON** — expected occasionally; the client strips fences and re-asks
  once. If the bake-off shows < 95 % first-try validity, follow ADR-0013 and switch model.
