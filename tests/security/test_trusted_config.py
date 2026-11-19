"""E1 trusted configuration: in CI mode nothing in the pull request's tree configures the engine."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from emissiongate import config
from emissiongate.config import UntrustedInput, check_trusted, load_settings
from emissiongate.tools import gitrefs

ROOT = Path(__file__).resolve().parents[2]
EG_VARS = (
    "EG_POLICY",
    "EG_TOFU_BIN",
    "EG_TOFU_PLUGIN_DIR",
    "EG_DATA_DIR",
    "EG_RUNS_DIR",
    "EG_FACTORS_DIR",
    "EG_GRID_SNAPSHOT_DIR",
    "EG_PREDICTIONS_DIR",
    "EG_ESTATE_DIR",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # load_dotenv writes into os.environ. setenv records the original value so teardown restores
    # it (or removes the variable), even when a test's load_settings() added it.
    for name in EG_VARS:
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


def _hostile_tree(tmp: Path) -> Path:
    """A pull request's working tree that tries to configure the engine."""
    tree = tmp / "pr"
    tree.mkdir()
    (tree / ".env").write_text(
        "EG_TOFU_BIN=./evil.sh\nEG_POLICY=./lax.yaml\nEG_TOFU_PLUGIN_DIR=./mirror\n",
        encoding="utf-8",
    )
    (tree / "policy.yaml").write_text("gate:\n  ack_kg_co2e_yr: 1.0e12\n", encoding="utf-8")
    (tree / "suppressions.yaml").write_text("suppressions: []\n", encoding="utf-8")
    return tree


def test_ci_mode_ignores_dotenv_and_policy_in_the_working_directory(tmp_path: Path) -> None:
    tree = _hostile_tree(tmp_path)
    s = load_settings(tree, ci=True)
    assert s.ci
    assert s.tofu_bin == "tofu"
    assert s.policy_path == config.PACKAGE_ROOT / "policy.yaml"
    assert s.suppressions_path == config.PACKAGE_ROOT / "suppressions.yaml"
    assert s.policy()["gate"]["ack_kg_co2e_yr"] == 100.0


def test_local_mode_still_reads_the_working_directory(tmp_path: Path) -> None:
    """The laptop workflow is unchanged: a developer's own .env and policy.yaml apply."""
    tree = _hostile_tree(tmp_path)
    s = load_settings(tree)
    assert s.policy_path == Path("./lax.yaml")
    assert s.tofu_bin == "./evil.sh"


def test_ci_mode_honours_the_job_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted = tmp_path / "org-config" / "policy.yaml"
    trusted.parent.mkdir()
    trusted.write_text((ROOT / "policy.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("EG_POLICY", str(trusted))
    s = load_settings(_hostile_tree(tmp_path), ci=True)
    assert s.policy_path == trusted


def test_ci_mode_refuses_paths_inside_the_pull_request_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "ws"
    tree = workspace / "estate"
    tree.mkdir(parents=True)
    monkeypatch.setenv("EG_DATA_DIR", "estate/data")
    monkeypatch.setenv("EG_TOFU_PLUGIN_DIR", "estate/.tofu-providers")
    s = load_settings(workspace, ci=True)
    found = check_trusted(s, tree)
    assert any("data_dir" in p for p in found)
    assert any("tofu_plugin_dir" in p for p in found)
    with pytest.raises(UntrustedInput):
        check_trusted(s, tree, strict=True)


def test_ci_mode_accepts_paths_outside_the_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "ws"
    tree = workspace / "estate"
    tree.mkdir(parents=True)
    monkeypatch.setenv("EG_DATA_DIR", str(tmp_path / "runner-temp" / "data"))
    monkeypatch.setenv("EG_TOFU_PLUGIN_DIR", str(tmp_path / "mirror"))
    s = load_settings(workspace, ci=True)
    assert check_trusted(s, tree) == []


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_policy_from_the_base_commit_not_the_head(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "sec-test")
    (repo / ".emissiongate").mkdir()
    (repo / ".emissiongate" / "policy.yaml").write_text("version: 1\nmarker: base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = gitrefs.rev_parse(repo, "HEAD")
    (repo / ".emissiongate" / "policy.yaml").write_text("version: 1\nmarker: head\n")
    _git(repo, "commit", "-q", "-am", "pr edits policy")
    assert (
        gitrefs.read_blob(repo, base, ".emissiongate/policy.yaml") == b"version: 1\nmarker: base\n"
    )
    assert gitrefs.read_blob(repo, base, ".emissiongate/absent.yaml") is None


def test_ci_refusal_is_ledgered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from emissiongate.core.ledger import Ledger
    from emissiongate.orchestrator.gate import Gate

    workspace = tmp_path / "ws"
    tree = workspace / "estate"
    tree.mkdir(parents=True)
    monkeypatch.setenv("EG_DATA_DIR", "estate/data")
    monkeypatch.setenv("EG_RUNS_DIR", str(tmp_path / "runs"))
    s = load_settings(workspace, ci=True)
    with pytest.raises(UntrustedInput):
        Gate(s, tree, "main", "HEAD", pr=7).run()
    (ledger_file,) = (tmp_path / "runs").glob("*/ledger.sqlite")
    events = Ledger(ledger_file, "read", lambda: None).events()  # type: ignore[arg-type,return-value]
    assert [(e.kind, e.state) for e in events] == [("error", "REFUSED")]
    assert events[0].detail["untrusted_inputs"] == 1


def test_untrusted_runs_dir_writes_nothing_inside_the_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from emissiongate.orchestrator.gate import Gate

    workspace = tmp_path / "ws"
    tree = workspace / "estate"
    tree.mkdir(parents=True)
    monkeypatch.setenv("EG_RUNS_DIR", "estate/runs")
    s = load_settings(workspace, ci=True)
    with pytest.raises(UntrustedInput):
        Gate(s, tree, "main", "HEAD", pr=7).run()
    assert not (tree / "runs").exists()
