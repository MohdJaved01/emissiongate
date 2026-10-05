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
