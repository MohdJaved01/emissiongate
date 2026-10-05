# Demo video — about 4 minutes, agent running, not slides

The video is used for pre-screening and must show the agent running. Record at 1080p: terminal on the
left (about 60%), browser on the right. Show real wall-clock time; where you cut a wait (for example the
GitHub Actions run), say so on screen ("1 minute later").

**Before recording**
- `make demo-offline score` passes: zero trap violations, recall at or above the threshold.
- Ollama is warm: `ollama run gpt-oss:20b "hi"` once, so the first call is not a cold start.
- The gate PR on `emissiongate-demo-estate` (branch `demo/add-gpu-fleet`) exists and its check has run.
- Close notifications. Use a large terminal font.

**Recording tools (free):** Windows Snipping Tool (screen recording) or Xbox Game Bar (`Win+Alt+R`), or
OBS Studio. Upload to YouTube as **Unlisted** (or a public Drive link) and paste the link at the top of
the README.

| Time | Screen | Say (roughly) |
|---|---|---|
| 0:00–0:20 | Estate repo on GitHub, a Terraform file | "Emissions are committed when this code merges. Nobody sees carbon at that moment. EmissionGate puts it in the pull request." |
| 0:20–0:40 | `make estate` output | "Everything is synthetic: ten resource groups with real-looking waste, and three traps that look like waste but must be refused." |
| 0:40–1:00 | `.venv/bin/emissiongate run --mode local --seed 42` → approval prompt → type yes | "Gate one: a human approves scope and budget. The agent can't start itself." |
| 1:00–1:40 | Quantifier table: kgCO2e/yr per resource with the provenance column | "Every number comes from deterministic code using published coefficients pinned to a commit. The model never computes a figure." |
| 1:40–2:00 | Ranking: carbon order vs cost order | "Ranked by carbon, not dollars. Archiving the log bucket saves money and almost no carbon; Graviton is the reverse." |
| 2:00–2:20 | Guardrail lines: DR standby, month-end batch, compliance logs | "The traps are refused before any decision is made. Fail closed." |
| 2:20–2:50 | LLM decision for one candidate (allowed options in, JSON out), then `tofu plan` OK | "The local open-weight model only chooses among options the code allows, and every change is proven with a plan." |
| 2:50–3:10 | `runs/<id>/prs/gpu-inference.md` | "The fix as a pull request: before and after, −258 kgCO2e a year, evidence and assumptions." |
| 3:10–3:30 | `report.html`: own-footprint block (energy, kgCO2e, tokens) and `make score` | "The agent measures its own energy, model included, and scores itself against the ground truth." |
| 3:30–4:20 | Browser: the gate PR adding 2 × g5.2xlarge. Comment: "+684 kgCO2e/yr (263–1,104, assumed load) — acknowledgement required", with a suggestion. Commit the suggestion (or add `eg/carbon-accepted` with a reason); the check re-runs | "That was waste found after the fact. This is the same engine stopping it before merge — and a human still decides." |
| 4:20–4:30 | README | "Synthetic data, open tools, open model. Code, design and the AI usage log are in the repo." |

If short of time, cut 1:40–2:00, not the gate.
