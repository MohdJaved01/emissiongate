"""The trust boundary, enforced (AGENTS.md invariant 2, import direction)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2] / "src" / "emissiongate"

CORE_ALLOWED_THIRD_PARTY = {"pydantic", "yaml"}
CORE_FORBIDDEN_STDLIB = {
    "subprocess",
    "socket",
    "urllib",
    "http",
    "ssl",
    "ftplib",
    "smtplib",
    "asyncio",
    "random",
}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
        elif isinstance(node, ast.ImportFrom) and node.level > 0:
            names.append("." * node.level + (node.module or ""))
    return names


def _modules(sub: str) -> list[Path]:
    return sorted((PKG / sub).rglob("*.py"))


def test_core_has_modules() -> None:
    assert _modules("core"), "core/ must exist"


@pytest.mark.parametrize("path", _modules("core"), ids=lambda p: p.name)
def test_core_imports_only_allowed(path: Path) -> None:
    for name in _imports(path):
        if name.startswith("."):
            # relative imports stay inside core
            continue
        top = name.split(".")[0]
        if top == "emissiongate":
            assert name == "emissiongate.contracts" or name.startswith("emissiongate.core"), (
                f"{path.name} imports {name}: core may import only contracts and core"
            )
            continue
        assert top not in CORE_FORBIDDEN_STDLIB, f"{path.name} imports {name} (network/subprocess)"
        assert top in sys.stdlib_module_names or top in CORE_ALLOWED_THIRD_PARTY, (
            f"{path.name} imports third-party {name}; core allows only pydantic and yaml"
        )


@pytest.mark.parametrize("sub", ["llm", "tools"])
def test_llm_and_tools_never_import_agents_or_orchestrator(sub: str) -> None:
    for path in _modules(sub):
        for name in _imports(path):
            assert not name.startswith(("emissiongate.agents", "emissiongate.orchestrator")), (
                f"{sub}/{path.name} imports {name}"
            )


def test_no_infrastructure_mutation_anywhere() -> None:
    """Invariant 3: no apply/destroy/import/state, no boto3, no terraform binary."""
    banned = ("boto3", "botocore")
    for path in PKG.rglob("*.py"):
        for name in _imports(path):
            assert name.split(".")[0] not in banned, f"{path.name} imports {name}"
        text = path.read_text(encoding="utf-8")
        for verb in ("apply", "destroy", "import", "state"):
            assert f'"{verb}", "-auto-approve"' not in text
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.List) and len(node.elts) >= 2:
                first, second = node.elts[0], node.elts[1]
                if isinstance(second, ast.Constant) and second.value in {
                    "apply",
                    "destroy",
                    "import",
                    "state",
                }:
                    assert not isinstance(first, ast.Constant | ast.Name | ast.Attribute), (
                        f"{path.name}: command list with '{second.value}'"
                    )
