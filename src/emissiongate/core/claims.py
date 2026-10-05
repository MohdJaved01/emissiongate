"""Numeric-claim scan for model prose (DATA_CONTRACTS validation rules, AGENTS.md invariant 1).

Digits adjacent to kg, kWh, t, %, $, USD or CO2 mean the prose is making a quantitative claim; such
prose is discarded and the deterministic template is used instead.
"""

from __future__ import annotations

import re

_UNIT = r"(?:kg|kwh|mwh|wh|t|tonnes?|tons?|%|usd|dollars?|co2e?|gco2e?|kgco2e?|w|watts?)"
PATTERNS = (
    re.compile(rf"\d[\d,.]*\s*{_UNIT}\b", re.IGNORECASE),
    re.compile(r"\d[\d,.]*\s*%", re.IGNORECASE),
    re.compile(r"(?:\$|usd|co2e?)\s*[:=]?\s*\d", re.IGNORECASE),
    re.compile(r"\d[\d,.]*\s*(?:per\s*cent|percent)\b", re.IGNORECASE),
)


def has_numeric_claim(text: str) -> bool:
    return any(p.search(text) for p in PATTERNS)


def any_numeric_claim(texts: list[str]) -> bool:
    return any(has_numeric_claim(t) for t in texts)
