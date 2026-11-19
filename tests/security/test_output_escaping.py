"""E1 untrusted text in output, and visible coverage, in the gate comment. No tofu needed."""

from __future__ import annotations

import re

import pytest

from emissiongate.agents import reporter
from emissiongate.contracts import GateResult, GateSuggestion, Projection, ResourceChange
from emissiongate.core.factors import Factors
from emissiongate.report import sanitize

GATE_CFG = {
    "warn_kg_co2e_yr": 25.0,
    "ack_kg_co2e_yr": 100.0,
    "ack_label": "eg/carbon-accepted",
    "assumed_utilisation_band": [0.1, 0.9],
    "assumed_gpu_utilisation": 0.5,
}
EVIL = (
    'x"] | <img src=x onerror=alert(1)> @octocat [click](https://evil.example) '
    "www.evil.example #1 ```\n## Approved"
)


def _render(result: GateResult, reason: str | None = None, notes: list[str] | None = None) -> str:
    return reporter.gate_comment(
        result, GATE_CFG, Factors.load(), 35, 1.0, None, None, reason, notes or []
    )


def _result(**kw) -> GateResult:
    base = {
        "pr_number": 7,
        "base_sha": "b" * 40,
        "head_sha": "a" * 40,
        "status": "pass",
        "net_kg_co2e_yr": 0.0,
        "net_kg_co2e_yr_low": 0.0,
        "net_kg_co2e_yr_high": 0.0,
        "changes": [],
        "projections": [],
        "suggestions": [],
        "ledger_run_id": "run-1",
    }
    base.update(kw)
    return GateResult(**base)


CODE_SPAN = re.compile(r"(?<![`\\])(`+)(?!`)(.+?)(?<!`)\1(?!`)")


def _assert_inert(md: str) -> None:
    """Nothing from EVIL renders as HTML, a mention, a link, a heading or a fence break.

    Code spans render their content literally, so only the text outside them is checked.
    """
    md = CODE_SPAN.sub("", md)
    assert "<img" not in md
    assert "@octocat" not in md
    assert "](https://evil.example)" not in md
    assert "https://evil.example" not in md
    assert "www.evil.example" not in md
    assert "\n## Approved" not in md


def test_unquantified_address_and_reason_are_escaped() -> None:
    addr = f'aws_instance.x["{EVIL}"]'
    p = Projection(
        address=addr,
        basis="assumed",
        kg_co2e_yr_before=0,
        kg_co2e_yr_after=0,
        kwh_yr_delta=0,
        usd_synthetic_yr_delta=0,
        provenance=[],
        quantified=False,
        reason=f"no factor for instance type {EVIL}",
    )
    ch = ResourceChange(address=addr, change="added", carbon_relevant=True, after={})
    md = _render(_result(changes=[ch], projections=[p], status="not_evaluated"), reason=EVIL)
    _assert_inert(md)


def test_tofu_errors_and_notes_are_escaped() -> None:
    md = _render(_result(status="not_evaluated"), reason=EVIL, notes=[EVIL])
    _assert_inert(md)


def test_acceptance_reason_is_escaped_and_capped() -> None:
    md = _render(_result(status="accepted", accepted_by="alice", accepted_reason=EVIL + "y" * 5000))
    _assert_inert(md)
    assert "y" * 600 not in md


def test_diff_cannot_close_its_fence() -> None:
    s = GateSuggestion(
        address="aws_autoscaling_group.a",
        template="schedule",
        params={"on_cron": "0 8 * * MON-FRI"},
        kg_co2e_yr_delta_vs_head=-1.0,
        plan_ok=True,
        diff="+ x\n```\n## Approved\n<img src=x>\n",
    )
    p = Projection(
        address="aws_autoscaling_group.a",
        basis="observed",
        kg_co2e_yr_before=0,
        kg_co2e_yr_after=200,
        kwh_yr_delta=1,
        usd_synthetic_yr_delta=1,
        provenance=[],
    )
    md = _render(_result(status="ack_required", projections=[p], suggestions=[s]))
    fence = re.search(r"^(`{3,})diff$", md, re.M)
    assert fence and len(fence.group(1)) > 3
    body = md[fence.end() :]
    assert body.index("## Approved") < body.index(fence.group(1))


@pytest.mark.parametrize(
    ("kind", "value", "ok"),
    [
        ("instance_type", "g5.2xlarge", True),
        ("instance_type", "m7g.metal-48xl", True),
        ("instance_type", "<b>x</b>", False),
        ("region", "us-east-1", True),
        ("region", "us-gov-west-1", True),
        ("region", "us-east-1 @octocat", False),
        ("number", "8760", True),
        ("number", "1e9; rm", False),
    ],
)
def test_attribute_values_are_validated_before_display(kind: str, value: str, ok: bool) -> None:
    assert (sanitize.checked(kind, value) == value) is ok


def test_inline_code_survives_backticks_and_pipes() -> None:
    out = sanitize.code("a`b|c")
    assert out.startswith("``") and "\\|" in out


def test_every_comment_states_coverage() -> None:
    changes = [
        ResourceChange(address="aws_instance.a", change="added", carbon_relevant=True),
        ResourceChange(address="aws_iam_role.r", change="changed", carbon_relevant=False),
    ]
    p = Projection(
        address="aws_instance.a",
        basis="assumed",
        kg_co2e_yr_before=0,
        kg_co2e_yr_after=0,
        kwh_yr_delta=0,
        usd_synthetic_yr_delta=0,
        provenance=[],
        quantified=False,
        reason="unknown: region",
    )
    md = _render(_result(changes=changes, projections=[p], status="not_evaluated"), "nothing")
    assert "**Coverage:** 2 changed resources seen · 0 quantified · 1 not quantified · " in md
    assert "1 not carbon-relevant" in md
