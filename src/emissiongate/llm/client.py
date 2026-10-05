"""LLM client protocol and the structured-call loop (llm/AGENTS.md).

Every structured call sends the pydantic JSON schema as `format`, reads `message.content` only,
strips a Markdown fence and validates with pydantic; on failure it re-asks once with the validation
error, then returns None so the caller takes the deterministic path. `message.thinking` is never
kept, only its hash.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ValidationError

FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class LLMTransport(Protocol):
    """One chat round trip. Returns Ollama's /api/chat response shape."""

    def chat(
        self,
        model: str,
        think: str,
        messages: list[dict[str, str]],
        schema: dict,
        temperature: float,
    ) -> dict: ...


@dataclass(frozen=True)
class Tier:
    model: str
    think: str

    @property
    def label(self) -> str:
        return f"{self.model}@{self.think}"


@dataclass(frozen=True)
class CallRecord:
    model: str
    think: str
    prompt_tokens: int
    completion_tokens: int  # eval_count: includes thinking tokens
    duration_ms: int
    attempt: int
    outcome: str  # valid | reasked | invalid | error
    thinking_sha256: str | None
    error: str | None = None


def strip_fences(text: str) -> str:
    match = FENCE.match(text)
    return match.group(1) if match else text.strip()


def _record(tier: Tier, resp: dict, attempt: int, outcome: str, error: str | None) -> CallRecord:
    thinking = (resp.get("message") or {}).get("thinking")
    return CallRecord(
        model=tier.model,
        think=tier.think,
        prompt_tokens=int(resp.get("prompt_eval_count") or 0),
        completion_tokens=int(resp.get("eval_count") or 0),
        duration_ms=int((resp.get("total_duration") or 0) / 1_000_000),
        attempt=attempt,
        outcome=outcome,
        thinking_sha256=hashlib.sha256(thinking.encode()).hexdigest() if thinking else None,
        error=error,
    )


def structured[M: BaseModel](
    transport: LLMTransport,
    tier: Tier,
    messages: list[dict[str, str]],
    schema_model: type[M],
    temperature: float,
) -> tuple[M | None, list[CallRecord]]:
    schema = schema_model.model_json_schema()
    records: list[CallRecord] = []
    convo = list(messages)
    for attempt in (1, 2):
        try:
            resp = transport.chat(tier.model, tier.think, convo, schema, temperature)
        except Exception as exc:  # connection errors: the caller falls back to the rule path
            records.append(
                CallRecord(tier.model, tier.think, 0, 0, 0, attempt, "error", None, str(exc)[:200])
            )
            return None, records
        content = strip_fences((resp.get("message") or {}).get("content") or "")
        try:
            parsed = schema_model.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            error = str(exc)[:500]
            records.append(_record(tier, resp, attempt, "invalid", error))
            convo = [
                *convo,
                {"role": "assistant", "content": content[:2000]},
                {
                    "role": "user",
                    "content": "Your reply did not validate against the JSON schema: "
                    f"{error}\nReply again with JSON only, matching this schema exactly:\n"
                    f"{json.dumps(schema)}",
                },
            ]
            continue
        records.append(_record(tier, resp, attempt, "valid" if attempt == 1 else "reasked", None))
        return parsed, records
    return None, records
