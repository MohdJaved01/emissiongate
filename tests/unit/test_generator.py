import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from emissiongate.contracts import GroundTruthEntry
from emissiongate.core.factors import Factors
from emissiongate.estate.generator import generate
from emissiongate.tools.tf import Workspace

ROOT = Path(__file__).resolve().parents[2]


def test_same_seed_gives_identical_manifest(tmp_path: Path, estate, factors: Factors) -> None:
    again = generate(42, tmp_path / "d", tmp_path / "e", ROOT / "tofu" / "versions.tf", factors)
    assert again["files"] == estate.manifest["files"]


def test_ground_truth_has_ten_entries_and_three_traps(estate) -> None:
    doc = json.loads((estate.data_dir / "ground_truth.json").read_text(encoding="utf-8"))
    assert doc["synthetic"] is True
    entries = [GroundTruthEntry(**e) for e in doc["entries"]]
    assert len(entries) == 10
    assert sorted(e.resource_id for e in entries if e.trap) == [
        "compliance-logs",
        "dr-standby",
        "monthend-close",
    ]


def test_versions_tf_is_copied(estate) -> None:
    copied = (estate.tf_dir / "versions.tf").read_text(encoding="utf-8")
    assert copied == (ROOT / "tofu" / "versions.tf").read_text(encoding="utf-8")


def test_outputs_are_labelled_synthetic(estate) -> None:
    table = pq.read_table(estate.data_dir / "cur" / "usage.parquet")
    assert table.schema.metadata[b"synthetic"] == b"true"
    assert all(table.column("synthetic").to_pylist())
    assert table.num_rows == 10 * 35 * 24
    prices = json.loads((estate.data_dir / "prices_synthetic.json").read_text(encoding="utf-8"))
    assert prices["synthetic"] is True
    for tf in estate.tf_dir.glob("*.tf"):
        if tf.name != "versions.tf":
            assert tf.read_text(encoding="utf-8").startswith("# synthetic: true")


def test_patterns_have_exact_target_means(estate) -> None:
    gpu = json.loads((estate.data_dir / "metrics" / "gpu-inference.json").read_text())
    assert sum(gpu["cpu"]) / len(gpu["cpu"]) == pytest.approx(0.05, abs=1e-12)
    assert sum(gpu["gpu"]) / len(gpu["gpu"]) == pytest.approx(0.04, abs=1e-12)
    db = json.loads((estate.data_dir / "metrics" / "reporting-db.json").read_text())
    assert sum(db["cpu"]) / len(db["cpu"]) == pytest.approx(0.05, abs=1e-12)


def test_telemetry_only_writes_no_terraform(tmp_path: Path, factors: Factors) -> None:
    manifest = generate(
        42, tmp_path / "d", tmp_path / "e", ROOT / "tofu" / "versions.tf", factors, True
    )
    assert not (tmp_path / "e").exists()
    assert not any(k.startswith("estate/") for k in manifest["files"])


@pytest.mark.tofu
def test_estate_validates_and_plans_offline(estate, tofu_cfg) -> None:
    with Workspace(tofu_cfg, estate.tf_dir) as ws:
        result = ws.check()
    assert result.ok, result.stderr_tail
