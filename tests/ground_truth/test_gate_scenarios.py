"""M6.5 acceptance: the gate on four PRs against the seed-42 estate (offline, provider mirror)."""

from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from emissiongate.config import load_settings
from emissiongate.core import hcl
from emissiongate.estate import terraform as tfw
from emissiongate.orchestrator.gate import Gate

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.tofu, pytest.mark.slow]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture(scope="module")
def pr_repo(tmp_path_factory, estate) -> Path:
    repo = tmp_path_factory.mktemp("estate-repo")
    for f in estate.tf_dir.glob("*.tf"):
        shutil.copy2(f, repo / f.name)
    _git(repo, "init", "-b", "main", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "gate-test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "estate")

    def branch(name: str, files: dict[str, str]) -> None:
        _git(repo, "checkout", "-q", "-b", name, "main")
        for rel, text in files.items():
            (repo / rel).write_text(text, encoding="utf-8", newline="\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", name)
        _git(repo, "checkout", "-q", "main")

    fleet = tfw.asg_blocks(
        "gpu-fleet", "us-east-1", "g5.2xlarge", 2, {"Environment": "staging", "Owner": "ml"}
    )
    branch("gpu", {"gpu_fleet.tf": hcl.render_file(fleet, "# synthetic: true")})
    lw = (estate.tf_dir / "legacy_worker.tf").read_text(encoding="utf-8")
    scaled = lw
    for key in ("max_size", "desired_capacity", "min_size"):
        scaled = hcl.set_attribute(
            scaled, "resource", ("aws_autoscaling_group", "legacy_worker"), key, "10"
        )
    branch("scale", {"legacy_worker.tf": scaled})
    branch("tags", {"legacy_worker.tf": lw.replace('"data"', '"data-platform"')})
    branch("broken", {"broken.tf": 'resource "aws_instance" "b" {\n  ami = \n}\n'})
    branch("unsafe", {"leak.tf": 'data "aws_caller_identity" "me" {}\n'})
    return repo


def _gate(tmp: Path, estate, repo: Path, head: str):
    settings = dataclasses.replace(
        load_settings(ROOT), cwd=ROOT, data_dir=estate.data_dir, runs_dir=tmp / "runs"
    )
    return Gate(settings, repo, "main", head).run()


def test_new_gpu_fleet_requires_acknowledgement(tmp_path, estate, pr_repo) -> None:
    run = _gate(tmp_path, estate, pr_repo, "gpu")
    r = run.result
    assert r.status == "ack_required"
    assert r.net_kg_co2e_yr == pytest.approx(683.517, abs=5e-3)
    assert r.net_kg_co2e_yr_low == pytest.approx(263.097, abs=5e-3)
    assert r.net_kg_co2e_yr_high == pytest.approx(1103.937, abs=5e-3)
    assert run.comment and "<!-- emissiongate-gate -->" in run.comment
    assert "assumed" in run.comment and "263.1" in run.comment
    sched = next(s for s in r.suggestions if s.template == "schedule")
    assert sched.plan_ok and sched.basis == "assumed"
    assert sched.kg_co2e_yr_delta_low is not None and sched.kg_co2e_yr_delta_high is not None
    assert sched.ledger_event_id and r.projection_event_id
    prediction = json.loads((run.run_dir / "prediction.json").read_text())
    assert prediction["head_sha"] == r.head_sha
    assert run.exit_code == 0  # without --post the gate only prints


def test_scale_out_warns_and_suggests_graviton(tmp_path, estate, pr_repo) -> None:
    r = _gate(tmp_path, estate, pr_repo, "scale").result
    assert r.status == "pass_with_warning"
    assert r.net_kg_co2e_yr == pytest.approx(59.195, abs=5e-3)
    g = next(s for s in r.suggestions if s.template == "graviton")
    assert g.plan_ok
    assert g.kg_co2e_yr_delta_vs_head == pytest.approx(-232.217, abs=5e-3)


def test_tags_only_produces_no_comment(tmp_path, estate, pr_repo) -> None:
    run = _gate(tmp_path, estate, pr_repo, "tags")
    assert run.comment is None
    assert run.result.status == "pass"


def test_data_source_is_not_planned(tmp_path, estate, pr_repo) -> None:
    run = _gate(tmp_path, estate, pr_repo, "unsafe")
    assert run.result.status == "not_evaluated"
    assert "safety" in (run.comment or "")


def test_invalid_hcl_is_not_evaluated_and_passes(tmp_path, estate, pr_repo) -> None:
    run = _gate(tmp_path, estate, pr_repo, "broken")
    assert run.result.status == "not_evaluated"
    assert run.exit_code == 0
    assert "Invalid expression" in (run.comment or "")
