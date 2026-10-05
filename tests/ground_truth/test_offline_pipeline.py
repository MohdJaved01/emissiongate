"""Offline pipeline on seed 42 vs ground truth (SYNTHETIC_ESTATE §4, BUILD_PLAN M6)."""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from pathlib import Path

import pytest

from emissiongate.config import load_settings
from emissiongate.contracts import GroundTruthEntry
from emissiongate.core.scoring import score
from emissiongate.orchestrator.machine import Machine

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.tofu, pytest.mark.slow]


def _settings(tmp: Path, estate):
    return dataclasses.replace(
        load_settings(ROOT),
        cwd=ROOT,
        data_dir=estate.data_dir,
        estate_dir=estate.tf_dir,
        runs_dir=tmp / "runs",
        grid_snapshot_dir=tmp / "no-snapshot",
    )


@pytest.fixture(scope="module")
def offline_run(tmp_path_factory, estate, tofu_cfg):
    tmp = tmp_path_factory.mktemp("offline")
    return Machine(_settings(tmp, estate), "offline", 42, "pytest").run()


def test_run_writes_ledger_manifest_report_and_drafts(offline_run) -> None:
    d = offline_run.run_dir
    for name in ("ledger.sqlite", "manifest.json", "report.html", "checkpoint.json"):
        assert (d / name).exists(), name
    assert sorted(p.name for p in (d / "prs").glob("*.md")) == [
        "dev-api.md",
        "gpu-inference.md",
        "legacy-worker.md",
        "reporting-db.md",
    ]
    m = offline_run.manifest
    assert m.final_state == "DONE"
    assert m.approved_by == "pytest"
    assert m.llm["calls"] == 0
    assert m.first_attempt_plan_success == 1.0
    assert json.loads((d / "checkpoint.json").read_text())["state"] == "DONE"


def test_ground_truth_thresholds(offline_run, estate) -> None:
    truth = [
        GroundTruthEntry(**e)
        for e in json.loads((estate.data_dir / "ground_truth.json").read_text())["entries"]
    ]
    prs = json.loads((offline_run.run_dir / "prs" / "index.json").read_text())
    s = score(truth, prs, [], [])
    assert s.precision == 1.0
    assert s.recall is not None and s.recall >= 0.8
    assert s.trap_violations == []
    assert not any("expiration" in text for p in prs for text in p["files"].values())


def test_every_transition_and_tool_call_is_ledgered(offline_run) -> None:
    con = sqlite3.connect(offline_run.run_dir / "ledger.sqlite")
    kinds = dict(con.execute("SELECT kind, count(*) FROM events GROUP BY kind").fetchall())
    states = [r[0] for r in con.execute("SELECT state FROM events WHERE kind='transition'")]
    con.close()
    assert states == ["COLLECTING", "QUANTIFIED", "RANKED", "DELIVERING", "DONE"]
    assert kinds["human_gate"] == 1
    assert kinds["tool_call"] >= 12


def test_pr_body_numbers_come_from_core(offline_run) -> None:
    body = (offline_run.run_dir / "prs" / "gpu-inference.md").read_text(encoding="utf-8")
    assert "| **kgCO2e / year** | 401.5 | 143.4 | **−258.1** |" in body
    assert "synthetic" in body.lower()


def test_injected_bad_param_is_repaired(tmp_path, estate, tofu_cfg) -> None:
    result = Machine(
        _settings(tmp_path, estate), "offline", 42, "pytest", inject=("bad-param",)
    ).run()
    graviton = next(d for d in result.drafts if d.candidate_id == "legacy-worker:graviton")
    assert graviton.status == "drafted"
    assert result.manifest.repair_attempts == 1
    assert result.manifest.first_attempt_plan_success == pytest.approx(0.75)
