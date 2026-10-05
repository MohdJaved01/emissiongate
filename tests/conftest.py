from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from emissiongate.config import load_settings
from emissiongate.core.factors import Factors
from emissiongate.estate.generator import generate
from emissiongate.tools.tf import TofuConfig, TofuError, check_ready

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class EstatePaths:
    data_dir: Path
    tf_dir: Path
    manifest: dict


@pytest.fixture(scope="session")
def factors() -> Factors:
    return Factors.load()


@pytest.fixture(scope="session")
def estate(tmp_path_factory: pytest.TempPathFactory, factors: Factors) -> EstatePaths:
    base = tmp_path_factory.mktemp("estate42")
    data, tf = base / "data", base / "estate"
    manifest = generate(42, data, tf, ROOT / "tofu" / "versions.tf", factors)
    return EstatePaths(data, tf, manifest)


@pytest.fixture(scope="session")
def tofu_cfg() -> TofuConfig:
    settings = load_settings(ROOT)
    cfg = TofuConfig(
        bin=settings.tofu_bin,
        plugin_dir=ROOT / ".tofu-providers",
        data_dir=ROOT / ".eg-cache" / "tofu-data",
    )
    try:
        check_ready(cfg)
    except TofuError as exc:
        pytest.skip(f"tofu not available: {exc}")
    return cfg


def make_context(tmp: Path, estate: EstatePaths, factors: Factors, mode: str = "offline"):
    import json
    from datetime import UTC, date, datetime

    from emissiongate.agents.context import RunContext
    from emissiongate.core.interventions import Prices
    from emissiongate.core.ledger import Ledger
    from emissiongate.core.policy import Policy

    settings = load_settings(ROOT)
    ledger = Ledger(tmp / "ledger.sqlite", "test-run", lambda: datetime(2026, 10, 5, tzinfo=UTC))
    prices = json.loads((estate.data_dir / "prices_synthetic.json").read_text(encoding="utf-8"))
    return RunContext(
        run_id="test-run",
        run_dir=tmp,
        mode=mode,
        data_dir=estate.data_dir,
        estate_dir=estate.tf_dir,
        factors=factors,
        policy=Policy.from_docs(settings.policy(), settings.suppressions()),
        ledger=ledger,
        tofu=TofuConfig(
            bin=settings.tofu_bin,
            plugin_dir=ROOT / ".tofu-providers",
            data_dir=ROOT / ".eg-cache" / "tofu-data",
        ),
        reference=datetime(2026, 10, 1, tzinfo=UTC),
        today=date(2026, 10, 5),
        prices=Prices.from_doc(prices),
    )


@pytest.fixture(scope="session")
def strategy(tmp_path_factory: pytest.TempPathFactory, estate: EstatePaths, factors: Factors):
    from emissiongate.agents import collector, quantifier, strategist

    ctx = make_context(tmp_path_factory.mktemp("run"), estate, factors)
    facts, _ = collector.collect(ctx)
    records, _ = quantifier.quantify(ctx, facts)
    return ctx, records, strategist.strategise(ctx, facts, records)
