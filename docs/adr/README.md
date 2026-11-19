# Architecture decision records

Short, immutable records. To change a decision, add a new ADR that supersedes the old one.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-deterministic-core.md) | The deterministic core computes every published number | accepted |
| [0002](0002-plain-state-machine.md) | Plain Python state machine, no agent framework | accepted |
| [0003](0003-no-apply-capability.md) | The agent has no capability to change infrastructure | accepted |
| [0004](0004-local-open-weight-llm.md) | Local open-weight LLM via Ollama (Qwen, Apache-2.0) | superseded by 0013 |
| [0005](0005-patch-templates.md) | Patch templates with parameters, not free-form HCL | accepted |
| [0006](0006-opentofu.md) | OpenTofu instead of Terraform CLI | accepted |
| [0007](0007-grid-intensity-tiers.md) | Grid intensity tiers: annual for totals, UK live/snapshot for time-shifting | accepted |
| [0008](0008-two-repositories.md) | Two repositories: the agent and the estate it changes | accepted |
| [0009](0009-local-runtime-only.md) | Local runtime only; no cloud deployment, server or dashboard | accepted; amended by 0018 |
| [0010](0010-rank-by-carbon.md) | Rank by carbon, report cost alongside | accepted |
| [0011](0011-github-httpx-rest.md) | GitHub via httpx REST, not PyGithub | accepted |
| [0012](0012-agents-md-canonical.md) | AGENTS.md is canonical; Codex is the primary development tool | accepted; primary tool amended by 0016 |
| [0013](0013-gpt-oss-runtime-model.md) | Runtime model: gpt-oss-20b, one resident model, two reasoning levels | accepted, pending bake-off |
| [0014](0014-offline-provider-mirror.md) | Offline OpenTofu provider mirror | accepted |
| [0015](0015-pr-gate-in-ci.md) | PR gate runs in CI on the infrastructure repo, deterministic, human-acknowledged | accepted; amended by 0018 |
| [0016](0016-claude-code-builds-submission.md) | Claude Code builds the submission; the repository stays Codex-ready | accepted |
| [0017](0017-native-windows-build-linux-ci-referee.md) | Build on native Windows; Linux CI is the referee | accepted; amends 0016 (environment) |
| [0018](0018-customer-run-plugin.md) | Customer-run plugin: CLI, image, GitHub Action, plan-JSON mode; no hosted service in v1 | accepted; amends 0009, 0015 |
| [0019](0019-telemetry-read-path.md) | Telemetry and billing read from customer-staged exports in v1 | accepted |
| [0020](0020-invariants-for-customer-data.md) | Invariants for customer data, CI egress and short-lived credentials | accepted; amends AGENTS.md invariants |
| [0021](0021-support-matrix-and-compatibility.md) | Support matrix, compatibility contract and v1 targets | accepted |
| [0022](0022-gate-fails-closed-when-it-cannot-trust-its-result.md) | The gate fails closed when it cannot trust or read its own result | accepted; clarifies invariants 6 and 14 |
