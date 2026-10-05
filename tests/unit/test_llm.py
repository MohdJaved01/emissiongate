"""M7 LLM layer with a fake transport: no Ollama, no network (AGENTS.md testing rules)."""

from __future__ import annotations

import json
import sqlite3

import pytest

from emissiongate.agents import decider
from emissiongate.contracts import Narrative, PatchDecision
from emissiongate.llm.client import Tier, strip_fences, structured
from emissiongate.llm.factory import LLM

SMALL, LARGE = Tier("fake-small", "low"), Tier("fake-large", "medium")


class FakeTransport:
    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []

    def chat(self, model, think, messages, schema, temperature) -> dict:
        self.calls.append({"model": model, "think": think, "temperature": temperature})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return {
            "message": {"content": content, "thinking": "private chain of thought"},
            "prompt_eval_count": 120,
            "eval_count": 45,
            "total_duration": 2_000_000_000,
        }


def test_strip_fences() -> None:
    assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_fences('{"a": 1}') == '{"a": 1}'


def test_valid_fenced_json_first_try() -> None:
    t = FakeTransport('```json\n{"summary": "Fine.", "risks": []}\n```')
    parsed, recs = structured(t, SMALL, [], Narrative, 0.3)
    assert parsed is not None and parsed.summary == "Fine."
    assert [r.outcome for r in recs] == ["valid"]
    assert recs[0].completion_tokens == 45 and recs[0].duration_ms == 2000
    assert recs[0].thinking_sha256 and "private" not in json.dumps(recs[0].__dict__)


def test_one_reask_then_valid() -> None:
    t = FakeTransport("not json", {"summary": "Second try.", "risks": []})
    parsed, recs = structured(t, SMALL, [], Narrative, 0.3)
    assert parsed is not None
    assert [r.outcome for r in recs] == ["invalid", "reasked"]


def test_two_invalid_replies_fall_back() -> None:
    t = FakeTransport("nope", {"wrong": True})
    parsed, recs = structured(t, SMALL, [], Narrative, 0.3)
    assert parsed is None and len(recs) == 2


def test_connection_error_falls_back() -> None:
    parsed, recs = structured(FakeTransport(ConnectionError("down")), SMALL, [], Narrative, 0.3)
    assert parsed is None and recs[0].outcome == "error"


def _with_llm(strategy, *replies):
    ctx, _, s = strategy
    ctx.llm = LLM(FakeTransport(*replies), SMALL, LARGE)
    return ctx, s


def test_llm_decision_within_allowed_values_is_used(strategy) -> None:
    cand = next(c for c in strategy[2].candidates if c.intervention == "schedule")
    padded = {o.name: o.allowed[-1] for o in cand.options}
    reply = {
        "candidate_id": cand.candidate_id,
        "template": "schedule",
        "params": padded,
        "rationale": "Padding avoids cold starts.",
    }
    ctx, s = _with_llm(strategy, reply)
    decision, source = decider.decide(ctx, s, cand)
    ctx.llm = None
    assert source == "llm" and decision.params == padded
    assert ctx.llm is None


def test_llm_decision_outside_allowed_values_falls_back(strategy) -> None:
    cand = strategy[2].candidates[0]
    bad = {
        "candidate_id": cand.candidate_id,
        "template": cand.intervention,
        "params": {o.name: "made-up" for o in cand.options},
        "rationale": "x",
    }
    ctx, s = _with_llm(strategy, bad)
    decision, source = decider.decide(ctx, s, cand)
    ctx.llm = None
    assert source == "rule" and decision.params == cand.default_params


def test_narrative_with_numbers_is_discarded(strategy) -> None:
    cand = strategy[2].candidates[0]
    claim = {"summary": "This saves 258 kg of CO2 every year.", "risks": []}
    ctx, s = _with_llm(strategy, claim)
    from emissiongate.agents.strategist import revalue, rule_decision

    text, _risks, source = decider.narrate(ctx, cand, revalue(ctx, s, rule_decision(cand)))
    ctx.llm = None
    assert source == "template" and "258" not in text


def test_llm_calls_are_ledgered_with_tokens_and_no_thinking(strategy) -> None:
    cand = strategy[2].candidates[0]
    ctx, s = _with_llm(strategy, {"summary": "Reasonable change.", "risks": ["Check usage."]})
    from emissiongate.agents.strategist import revalue, rule_decision

    _text, risks, source = decider.narrate(ctx, cand, revalue(ctx, s, rule_decision(cand)))
    ctx.llm = None
    assert source == "llm" and risks == ["Check usage."]
    con = sqlite3.connect(ctx.ledger.path)
    rows = con.execute(
        "SELECT model, prompt_tokens, completion_tokens, detail FROM events WHERE kind='llm_call'"
    ).fetchall()
    con.close()
    assert rows
    model, pt, ct, detail = rows[-1]
    assert model == "fake-small@low" and (pt, ct) == (120, 45)
    assert "private chain of thought" not in detail and "thinking_sha256" in detail


def test_patch_decision_schema_has_no_numbers() -> None:
    props = PatchDecision.model_json_schema()["properties"]
    assert all(p.get("type") != "number" for p in props.values())


@pytest.mark.parametrize("provider", ["none", "openai_compat"])
def test_disabled_provider_means_offline(provider: str) -> None:
    import dataclasses

    from emissiongate.config import load_settings
    from emissiongate.llm.factory import make_client

    client, note = make_client(dataclasses.replace(load_settings(), llm_provider=provider))
    assert client is None and "offline" in note
