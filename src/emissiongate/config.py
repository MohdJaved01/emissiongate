"""Settings from the environment (.env, never secrets), policy.yaml and suppressions.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # repo root for an editable install


def _first_existing(*candidates: Path) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, "")
    return value if value.strip() else default


@dataclass(frozen=True)
class Settings:
    cwd: Path
    data_dir: Path
    estate_dir: Path
    runs_dir: Path
    factors_dir: Path
    policy_path: Path
    suppressions_path: Path
    versions_tf: Path
    tofu_bin: str
    tofu_plugin_dir: Path
    llm_provider: str
    ollama_url: str
    model_small: str
    model_large: str
    think_small: str
    think_large: str
    num_ctx: int
    country_iso: str
    device_embodied_kg_co2e: float | None
    device_lifespan_years: float
    grid_snapshot_dir: Path
    predictions_dir: Path

    def policy(self) -> dict:
        return load_yaml(self.policy_path)

    def suppressions(self) -> dict:
        return load_yaml(self.suppressions_path)


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    if not isinstance(doc, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    return doc


def load_settings(cwd: Path | None = None) -> Settings:
    cwd = (cwd or Path.cwd()).resolve()
    # .env.example carries the committed defaults; .env (if any) overrides. Neither holds secrets.
    for env_file in (cwd / ".env", cwd / ".env.example", PACKAGE_ROOT / ".env.example"):
        if env_file.exists():
            load_dotenv(env_file, override=False)
    embodied = _env("EG_DEVICE_EMBODIED_KG_CO2E")
    return Settings(
        cwd=cwd,
        data_dir=cwd / _env("EG_DATA_DIR", "data"),
        estate_dir=(cwd / _env("EG_ESTATE_DIR", ".estate")).resolve(),
        runs_dir=cwd / _env("EG_RUNS_DIR", "runs"),
        factors_dir=Path(_env("EG_FACTORS_DIR", str(PACKAGE_ROOT / "factors"))),
        policy_path=Path(
            _env(
                "EG_POLICY", str(_first_existing(cwd / "policy.yaml", PACKAGE_ROOT / "policy.yaml"))
            )
        ),
        suppressions_path=_first_existing(
            cwd / "suppressions.yaml", PACKAGE_ROOT / "suppressions.yaml"
        ),
        versions_tf=PACKAGE_ROOT / "tofu" / "versions.tf",
        tofu_bin=_env("EG_TOFU_BIN", "tofu"),
        tofu_plugin_dir=(cwd / _env("EG_TOFU_PLUGIN_DIR", ".tofu-providers")).resolve(),
        llm_provider=_env("EG_LLM_PROVIDER", "ollama"),
        ollama_url=_env("EG_OLLAMA_URL", "http://localhost:11434"),
        model_small=_env("EG_MODEL_SMALL"),
        model_large=_env("EG_MODEL_LARGE"),
        think_small=_env("EG_THINK_SMALL", "low"),
        think_large=_env("EG_THINK_LARGE", "medium"),
        num_ctx=int(_env("EG_NUM_CTX", "16384")),
        country_iso=_env("EG_COUNTRY_ISO", "IND"),
        device_embodied_kg_co2e=float(embodied) if embodied else None,
        device_lifespan_years=float(_env("EG_DEVICE_LIFESPAN_YEARS", "4")),
        grid_snapshot_dir=Path(
            _env("EG_GRID_SNAPSHOT_DIR", str(PACKAGE_ROOT / "fixtures" / "grid"))
        ),
        predictions_dir=Path(
            _env("EG_PREDICTIONS_DIR", str(PACKAGE_ROOT / "fixtures" / "predictions"))
        ),
    )
