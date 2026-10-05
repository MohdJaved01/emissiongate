"""Build the LLM client from config; model names and think levels come only from EG_* settings."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from emissiongate.config import Settings
from emissiongate.llm.client import LLMTransport, Tier
from emissiongate.llm.ollama import OllamaTransport


@dataclass(frozen=True)
class LLM:
    transport: LLMTransport
    small: Tier  # planning, classification, narrative (EG_THINK_SMALL)
    large: Tier  # patch decision, parameter repair (EG_THINK_LARGE)


def make_client(settings: Settings) -> tuple[LLM | None, str]:
    """Return (client, note). Without a reachable model the run continues in offline behaviour."""
    if settings.llm_provider != "ollama":
        return None, (
            f"LLM provider {settings.llm_provider!r} is not enabled in this build; "
            "the run uses offline behaviour (rule-based choices, templated prose)."
        )
    if not settings.model_small or not settings.model_large:
        return None, "EG_MODEL_SMALL/EG_MODEL_LARGE not set; offline behaviour."
    transport = OllamaTransport(settings.ollama_url, settings.num_ctx)
    try:
        models = transport.available_models()
    except httpx.HTTPError as exc:
        return None, (
            f"Ollama not reachable at {settings.ollama_url} ({type(exc).__name__}); the run "
            "continued in offline behaviour (rule-based choices, templated prose)."
        )
    missing = sorted({settings.model_small, settings.model_large} - set(models))
    if missing:
        return None, f"Ollama has no {', '.join(missing)} (run `make models`); offline behaviour."
    small = Tier(settings.model_small, settings.think_small)
    large = Tier(settings.model_large, settings.think_large)
    return LLM(transport, small, large), (
        f"Local LLM: {small.label} (narrative), {large.label} (decisions, repair) via Ollama. "
        "The model chooses among allowed options and writes prose; every number comes from the "
        "deterministic core."
    )
