"""M5: every template renders a minimal diff and passes fmt/validate/plan offline."""

from __future__ import annotations

import difflib

import pytest

from emissiongate.contracts import Candidate, ParamOption, PatchDecision, Resource
from emissiongate.core import patches
from emissiongate.tools.tf import Workspace

CASES = {
    "rightsize-rds": (
        "rightsize",
        "reporting_db.tf",
        Resource(
            resource_id="reporting-db",
            kind="rds",
            region="us-east-1",
            instance_type="db.r5.4xlarge",
            tags={},
            tf_file="reporting_db.tf",
            tf_address="aws_db_instance.reporting_db",
        ),
        {"target_instance_type": "db.r5.xlarge"},
    ),
    "rightsize-asg": (
        "rightsize",
        "gpu_inference.tf",
        Resource(
            resource_id="gpu-inference",
            kind="ec2_asg",
            region="us-east-1",
            tags={},
            tf_file="gpu_inference.tf",
            tf_address="aws_autoscaling_group.gpu_inference",
        ),
        {"target_instance_type": "g5.xlarge"},
    ),
    "schedule": (
        "schedule",
        "gpu_inference.tf",
        Resource(
            resource_id="gpu-inference",
            kind="ec2_asg",
            region="us-east-1",
            tags={},
            tf_file="gpu_inference.tf",
            tf_address="aws_autoscaling_group.gpu_inference",
        ),
        {
            "on_cron": "0 8 * * MON-FRI",
            "off_cron": "0 20 * * MON-FRI",
            "time_zone": "America/New_York",
            "min_on": "4",
        },
    ),
    "graviton": (
        "graviton",
        "legacy_worker.tf",
        Resource(
            resource_id="legacy-worker",
            kind="ec2_asg",
            region="eu-west-1",
            tags={},
            tf_file="legacy_worker.tf",
            tf_address="aws_autoscaling_group.legacy_worker",
        ),
        {"target_instance_type": "m7g.2xlarge", "image_param": "ami_arm64"},
    ),
    "storage_tier": (
        "storage_tier",
        "compliance_logs.tf",
        Resource(
            resource_id="compliance-logs",
            kind="s3",
            region="eu-west-2",
            tags={},
            tf_file="compliance_logs.tf",
            tf_address="aws_s3_bucket.compliance_logs",
        ),
        {"transition_days": "90", "storage_class": "GLACIER_IR"},
    ),
    "time_shift": (
        "time_shift",
        "nightly_etl.tf",
        Resource(
            resource_id="nightly-etl",
            kind="ec2_asg",
            region="eu-west-2",
            tags={},
            tf_file="nightly_etl.tf",
            tf_address="aws_autoscaling_group.nightly_etl",
        ),
        {"start_cron": "30 3 * * *"},
    ),
}


def _render(estate, case: str, inject: bool = False) -> tuple[str, dict[str, str]]:
    template, file, resource, params = CASES[case]
    text = (estate.tf_dir / file).read_text(encoding="utf-8")
    files = patches.render(template, resource, text, params, inject_bad_param=inject)
    return text, files


@pytest.mark.parametrize("case", sorted(CASES))
def test_render_is_a_minimal_diff_of_one_file(estate, case: str) -> None:
    old, files = _render(estate, case)
    assert list(files) == [CASES[case][1]]
    diff = [
        line
        for line in difflib.unified_diff(old.splitlines(), files[CASES[case][1]].splitlines())
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]
    removed = [line for line in diff if line.startswith("-")]
    assert len(removed) <= 2, diff  # changes edit at most two existing lines, never remove blocks


def test_time_shift_moves_both_recurrences(estate) -> None:
    _, files = _render(estate, "time_shift")
    text = files["nightly_etl.tf"]
    assert '"30 3 * * *"' in text and '"30 5 * * *"' in text


def test_storage_tier_never_has_expiration(estate) -> None:
    _, files = _render(estate, "storage_tier")
    assert "expiration" not in files["compliance_logs.tf"]
    assert "GLACIER_IR" in files["compliance_logs.tf"]


def test_params_outside_allowed_values_are_rejected() -> None:
    cand = Candidate(
        candidate_id="x:graviton",
        resource_id="x",
        intervention="graviton",
        options=[ParamOption(name="target_instance_type", allowed=["m7g.2xlarge"])],
        default_params={"target_instance_type": "m7g.2xlarge"},
        kg_co2e_saved_yr=1.0,
        kwh_saved_yr=1.0,
        usd_synthetic_saved_yr=1.0,
        rank_carbon=1,
        rank_cost=1,
        confidence="high",
    )
    bad = PatchDecision(
        candidate_id="x:graviton",
        template="graviton",
        params={"target_instance_type": "m8g.metal", "hcl": "anything"},
        rationale="",
    )
    errors = patches.validate_params(cand, bad)
    assert any("not in allowed" in e for e in errors)
    assert any("unknown parameter" in e for e in errors)


@pytest.mark.tofu
def test_every_template_passes_fmt_validate_plan(estate, tofu_cfg) -> None:
    with Workspace(tofu_cfg, estate.tf_dir) as ws:
        for case in sorted(CASES):
            _, files = _render(estate, case)
            result = ws.check(files)
            assert result.ok, f"{case}: {result.command}\n{result.stderr_tail}"
        _, bad = _render(estate, "graviton", inject=True)
        result = ws.check(bad)
        assert not result.ok
        assert "ami_arm64_latest" in result.stderr_tail
        assert len(result.stderr_tail.encode()) <= 4096
