"""E1/E7 reference workflows: least privilege, token never next to planning, actions pinned by SHA.

Static checks over the YAML. `zizmor` and `actionlint` run on top of these in CI later (E1).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ESTATE = ROOT / "estate-repo" / ".github" / "workflows"
EVALUATE = ESTATE / "emissiongate-gate.yml"
PUBLISH = ESTATE / "emissiongate-publish.yml"
ALL = sorted((ROOT / ".github" / "workflows").glob("*.yml")) + sorted(ESTATE.glob("*.yml"))
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on(wf: dict) -> dict:
    on = wf.get("on", wf.get(True))  # YAML 1.1 reads a bare `on` key as True
    return on if isinstance(on, dict) else {k: None for k in ([on] if isinstance(on, str) else on)}


def _steps(wf: dict) -> list[dict]:
    return [s for job in wf["jobs"].values() for s in job.get("steps", [])]


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_every_action_is_pinned_by_full_sha(path: Path) -> None:
    for step in _steps(_load(path)):
        if "uses" in step:
            assert PINNED.match(step["uses"]), f"{path.name}: {step['uses']} is not pinned by SHA"


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_no_pull_request_target(path: Path) -> None:
    assert "pull_request_target" not in _on(_load(path))


@pytest.mark.parametrize("path", sorted(ESTATE.glob("*.yml")), ids=lambda p: p.name)
def test_estate_workflows_grant_nothing_by_default(path: Path) -> None:
    wf = _load(path)
    assert wf["permissions"] == {}
    for step in _steps(wf):
        if str(step.get("uses", "")).startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] is False


def test_evaluate_job_has_no_token_and_cannot_write() -> None:
    wf = _load(EVALUATE)
    assert set(_on(wf)) == {"pull_request", "pull_request_review"}
    (job,) = wf["jobs"].values()
    assert job["permissions"] == {"contents": "read"}
    text = EVALUATE.read_text(encoding="utf-8")
    assert "github.token" not in text and "secrets." not in text and "GITHUB_TOKEN:" not in text
    runs = " ".join(s.get("run", "") for s in _steps(wf))
    assert "emissiongate gate --ci" in runs and "--post" not in runs


def test_publish_job_never_runs_pull_request_code() -> None:
    wf = _load(PUBLISH)
    assert set(_on(wf)) == {"workflow_run"}
    assert _on(wf)["workflow_run"]["workflows"] == [_load(EVALUATE)["name"]]
    (job,) = wf["jobs"].values()
    # Only the default branch's evaluate workflow at its own path may trigger a publish.
    assert (
        "github.event.workflow_run.path == '.github/workflows/emissiongate-gate.yml'" in job["if"]
    )
    assert job["permissions"] == {
        "actions": "read",
        "checks": "write",
        "pull-requests": "write",
        "issues": "read",
        "contents": "read",
    }
    for step in _steps(wf):
        ref = str((step.get("with") or {}).get("ref", ""))
        assert "head" not in ref and "pull" not in ref, f"publish checks out {ref!r}"
        run = step.get("run", "")
        assert (
            "tofu" not in run
            and "emissiongate gate " not in run
            and "pip install -e trusted" not in run
        )
    runs = " ".join(s.get("run", "") for s in _steps(wf))
    assert "emissiongate gate-publish" in runs
    assert '--head-sha "$HEAD_SHA"' in runs
    env = next(s["env"] for s in _steps(wf) if "gate-publish" in s.get("run", ""))
    assert env["HEAD_SHA"] == "${{ github.event.workflow_run.head_sha }}"
