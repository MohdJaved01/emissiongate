# AGENTS.md — src/emissiongate/llm

Applies to everything under `llm/`. The root `AGENTS.md` still applies; this file adds to it.

- The client talks to Ollama `/api/chat` with `stream: false`, `format` = the pydantic JSON schema,
  `think` = the configured level, and `options.num_ctx` / `options.temperature` set explicitly.
- Parse `message.content` only. Strip a leading/trailing Markdown code fence before `json.loads`.
  `message.thinking` never enters prompts, reports, PR bodies or ledger `detail` (store a hash if needed).
- Record for every call: model, think level, `prompt_eval_count`, `eval_count`, `total_duration`, attempt
  number, and outcome (`valid`, `reasked`, `fallback`).
- One re-ask with the validation error, then return `None` so the caller takes the deterministic path.
- Prompts are Jinja templates in `prompts/`. They receive typed facts and the allowed options; they never
  receive raw CUR rows, secrets, or numbers the model is expected to restate.
- The numeric-claim scan (digits next to kg, kWh, t, %, $, USD, CO2) runs on every narrative before use.
- No provider SDKs. `httpx` only. The hosted fallback speaks the OpenAI-compatible Chat Completions API
  and is disabled unless `EG_LLM_PROVIDER=openai_compat`.

## Code Review Rules

- **Model output used as data (P0).** Flag any path where parsed LLM output feeds a number into a report,
  ranking or savings calculation. Safe path: the model selects; `core/` computes.
- **Thinking leakage (P1).** Flag `message.thinking` written to logs, ledger detail, reports or prompts.
- **Unvalidated parse (P1).** Flag `json.loads` results used without pydantic validation, or retries beyond
  one re-ask.
- **Hard-coded model names (P1).** Flag model tags or think levels written as literals outside config.
- **Streaming (P1).** Flag `stream: true` for structured calls; enforcement is unreliable when streaming.
