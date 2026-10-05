"""Hard ceilings from policy.yaml -> ceilings (AGENTS.md invariant 9)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):
    def __init__(self, ceiling: str, used: float, limit: float) -> None:
        super().__init__(f"ceiling {ceiling} reached ({used} of {limit})")
        self.ceiling = ceiling


@dataclass
class Budget:
    ceilings: dict
    started: float = field(default_factory=time.monotonic)
    llm_calls: int = 0
    tokens: int = 0
    prs: int = 0
    repairs: int = 0

    def _limit(self, key: str) -> float:
        if key not in self.ceilings:
            raise KeyError(f"policy.yaml ceilings missing {key}")
        return float(self.ceilings[key])

    def check(self) -> None:
        elapsed = time.monotonic() - self.started
        for name, used in (
            ("max_wall_seconds", elapsed),
            ("max_llm_calls_per_run", self.llm_calls),
            ("max_tokens_per_run", self.tokens),
        ):
            if used >= self._limit(name):
                raise BudgetExceeded(name, used, self._limit(name))

    def can_call_llm(self) -> bool:
        return self.llm_calls < self._limit("max_llm_calls_per_run") and self.tokens < self._limit(
            "max_tokens_per_run"
        )

    def charge_llm(self, tokens: int) -> None:
        self.llm_calls += 1
        self.tokens += tokens

    def charge_repair(self) -> None:
        self.repairs += 1

    def pr_slot(self) -> bool:
        return self.prs < self._limit("max_prs_per_run")

    def charge_pr(self) -> None:
        self.prs += 1
