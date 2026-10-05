"""Shared run context handed to every agent by the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from emissiongate.core.factors import Factors
from emissiongate.core.interventions import Prices
from emissiongate.core.ledger import Ledger
from emissiongate.core.policy import Policy
from emissiongate.tools.tf import TofuConfig


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    mode: str  # offline | local | live
    data_dir: Path
    estate_dir: Path
    factors: Factors
    policy: Policy
    ledger: Ledger
    tofu: TofuConfig
    reference: datetime  # end of the telemetry window; injected, never the wall clock in core
    today: Any  # date, for suppression expiry
    prices: Prices | None = None
    llm: Any = None  # emissiongate.llm.client.LLMClient | None
    budget: Any = None  # emissiongate.orchestrator.budget.Budget (duck-typed)
    grid_snapshot: Any = None  # core.grid.GridSnapshot | None
    inject: tuple[str, ...] = ()
    state: str = "SCOPED"
    notes: list[str] = field(default_factory=list)
