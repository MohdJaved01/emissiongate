"""E1 split gate: the privileged publish step treats the evaluate artefact as untrusted.

THREAT_MODEL B5. No network: GitHub is mocked with respx; no tofu.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import subprocess
from pathlib import Path

import httpx
import pytest
import respx

from emissiongate.config import load_settings
from emissiongate.contracts import GateEvaluation, GateResult, Projection, ResourceChange
from emissiongate.core.ledger import Ledger
from emissiongate.orchestrator.publish import CHECK_NAME, MAX_EVALUATION_BYTES, Publisher
from emissiongate.tools.github import MARKER, GitHub

ROOT = Path(__file__).resolve().parents[2]
REPO = "owner/emissiongate-demo-estate"
BASE = f"https://api.github.com/repos/{REPO}"
HEAD = "a" * 40
OTHER = "c" * 40
ADDR = "aws_autoscaling_group.gpu_fleet"
REASON = "Needed for the Q4 model launch; schedule follows."


def _evaluation(
    *, after: float = 150.0, status: str = "ack_required", net: float | None = None, **result
) -> dict:
    p = Projection(
        address=ADDR,
        basis="observed",
        kg_co2e_yr_before=0.0,
        kg_co2e_yr_after=after,
        kwh_yr_delta=1.0,
        usd_synthetic_yr_delta=1.0,
        provenance=[],
    )
    ch = ResourceChange(
        address=ADDR,
        change="added",
        carbon_relevant=True,
        after={"instance_type": "g5.2xlarge", "count": "2", "region": "us-east-1"},
    )
    r = GateResult(
        pr_number=result.pop("pr_number", 7),
        base_sha="b" * 40,
        head_sha=result.pop("head_sha", HEAD),
        status=status,  # type: ignore[arg-type]
        net_kg_co2e_yr=after if net is None else net,
        net_kg_co2e_yr_low=after if net is None else net,
        net_kg_co2e_yr_high=after if net is None else net,
        changes=[ch],
        projections=[p],
        suggestions=[],
        ledger_run_id="20261119T000000Z-gate-pr7",
        **result,
    )
    ev = GateEvaluation(repo=REPO, result=r, comment=True, runtime_s=1.5)
    return json.loads(ev.model_dump_json())


def _artefact(tmp: Path, doc: dict | str | bytes, name: str = "run1") -> Path:
    root = tmp / "artefact"
    (root / name).mkdir(parents=True, exist_ok=True)
    data = doc if isinstance(doc, (str, bytes)) else json.dumps(doc)
    target = root / name / "evaluation.json"
    if isinstance(data, bytes):
        target.write_bytes(data)
    else:
        target.write_text(data, encoding="utf-8")
    return root


def _settings(tmp: Path):
    return dataclasses.replace(load_settings(ROOT, ci=True), runs_dir=tmp / "runs")


class Api:
    """GitHub mocks; records what the publisher wrote."""

    def __init__(
        self,
        pr_head: str = HEAD,
        check_status: int = 201,
        files: list[dict] | None = None,
        base_ref: str = "main",
        others: list[dict] | None = None,
    ) -> None:
        self.checks: list[dict] = []
        self.comments: list[str] = []
        pull = {"number": 7, "state": "open", "head": {"sha": pr_head}, "base": {"ref": base_ref}}
        respx.get(f"{BASE}/pulls/7").mock(return_value=httpx.Response(200, json=pull))
        respx.get(f"{BASE}/commits/{HEAD}/pulls").mock(
            return_value=httpx.Response(200, json=[pull, *(others or [])])
        )
        for o in others or []:
            respx.get(f"{BASE}/pulls/{o['number']}").mock(return_value=httpx.Response(200, json=o))
            respx.get(f"{BASE}/pulls/{o['number']}/files").mock(
                return_value=httpx.Response(200, json=o.get("_files", []))
            )
        default = [{"filename": "gpu_fleet.tf", "status": "added"}]
        respx.get(f"{BASE}/pulls/7/files").mock(
            return_value=httpx.Response(200, json=default if files is None else files)
        )
        respx.get(f"{BASE}/issues/7/comments").mock(return_value=httpx.Response(200, json=[]))
        respx.post(f"{BASE}/issues/7/comments").mock(side_effect=self._comment)
        respx.post(f"{BASE}/check-runs").mock(side_effect=self._check(check_status))
        self.labels = respx.get(f"{BASE}/issues/7/labels").mock(
            return_value=httpx.Response(200, json=[])
        )

    def _comment(self, request: httpx.Request) -> httpx.Response:
        self.comments.append(json.loads(request.content)["body"])
        return httpx.Response(201, json={"html_url": "https://github.com/c/1"})

    def _check(self, status: int):
        def handler(request: httpx.Request) -> httpx.Response:
            if status >= 400:
                return httpx.Response(status, json={"message": "Resource not accessible"})
            self.checks.append(json.loads(request.content))
            return httpx.Response(status, json={"html_url": "https://github.com/r/1"})

        return handler

    def accepted_by_alice(self) -> None:
        respx.get(f"{BASE}/issues/7/labels").mock(
            return_value=httpx.Response(200, json=[{"name": "eg/carbon-accepted"}])
        )
        respx.get(f"{BASE}/issues/7/events").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "event": "labeled",
                        "label": {"name": "eg/carbon-accepted"},
                        "actor": {"login": "alice", "type": "User"},
                    }
                ],
            )
        )
        review = {
            "body": REASON,
            "commit_id": HEAD,
            "state": "COMMENTED",
            "user": {"login": "alice", "type": "User"},
        }
        respx.get(f"{BASE}/pulls/7/reviews").mock(return_value=httpx.Response(200, json=[review]))
        respx.get(f"{BASE}/collaborators/alice/permission").mock(
            return_value=httpx.Response(200, json={"role_name": "write"})
        )


def _publish(tmp: Path, artefact: Path, **kw):
    gh = GitHub("test-token-not-real", REPO)
    head = kw.pop("head_sha", HEAD)
    return Publisher(_settings(tmp), artefact, REPO, head, gh, "main", **kw).run()


@respx.mock
def test_valid_evaluation_gets_a_comment_and_a_failing_check(tmp_path: Path) -> None:
    api = Api()
    run = _publish(tmp_path, _artefact(tmp_path, _evaluation()))
    assert (run.status, run.conclusion, run.exit_code) == ("ack_required", "failure", 1)
    assert len(api.comments) == 1 and MARKER in api.comments[0]
    (check,) = api.checks
    assert check["name"] == CHECK_NAME and check["head_sha"] == HEAD
    assert check["conclusion"] == "failure" and "+150.0" in check["output"]["title"]


@respx.mock
def test_status_and_net_are_rederived_from_projections(tmp_path: Path) -> None:
    """A forged "pass" with net 0 does not survive: the publisher recomputes in core."""
    api = Api()
    doc = _evaluation(after=150.0, status="pass", net=0.0)
    run = _publish(tmp_path, _artefact(tmp_path, doc))
    assert run.status == "ack_required"
    assert api.checks[0]["conclusion"] == "failure"
    result = json.loads((run.run_dir / "gate_result.json").read_text(encoding="utf-8"))
    assert result["net_kg_co2e_yr"] == pytest.approx(150.0)


@respx.mock
def test_not_evaluated_fails_by_default(tmp_path: Path) -> None:
    """GitHub counts neutral as passing a required check, so the shipped policy fails closed."""
    api = Api()
    doc = _evaluation(status="not_evaluated")
    doc["reason"] = "configuration not planned for safety"
    run = _publish(tmp_path, _artefact(tmp_path, doc))
    assert (run.status, run.conclusion, run.exit_code) == ("not_evaluated", "failure", 1)
    assert api.checks[0]["output"]["title"] == "not evaluated"


@respx.mock
def test_not_evaluated_can_be_neutral_by_policy(tmp_path: Path) -> None:
    api = Api()
    repo = _policy_repo(
        tmp_path, "not_evaluated_conclusion: failure", "not_evaluated_conclusion: neutral"
    )
    run = _publish(
        tmp_path, _artefact(tmp_path, _evaluation(status="not_evaluated")), config_repo=repo
    )
    assert (run.status, run.conclusion, run.exit_code) == ("not_evaluated", "neutral", 0)
    assert "passes as neutral" in api.comments[0]


@respx.mock
def test_pr_targeting_another_branch_fails_closed(tmp_path: Path) -> None:
    """The check belongs to the commit; a PR into another branch must not write it."""
    api = Api(base_ref="release-x")
    run = _publish(tmp_path, _artefact(tmp_path, _evaluation(after=0.0, status="pass")))
    assert run.conclusion == "failure" and "not the default branch" in (run.problem or "")
    assert api.comments == []


@pytest.mark.parametrize(
    "other",
    [
        {"number": 8, "state": "open", "head": {"sha": HEAD}, "base": {"ref": "release-x"}},
        {
            "number": 8,
            "state": "open",
            "head": {"sha": HEAD},
            "base": {"ref": "main"},
            "_files": [{"filename": ".github/workflows/emissiongate-gate.yml"}],
        },
    ],
    ids=["same-commit-other-base", "same-commit-edits-workflow"],
)
@respx.mock
def test_another_open_pr_on_the_commit_can_spoil_the_check(tmp_path: Path, other) -> None:
    """PR #8 has the same head commit; its own run could write the latest check on that commit
    (another base, or its own workflow files), so the check on the commit fails closed."""
    api = Api(others=[other])
    run = _publish(tmp_path, _artefact(tmp_path, _evaluation(after=0.0, status="pass")))
    assert run.conclusion == "failure" and "#8" in (run.problem or "")
    assert api.comments == []


@respx.mock
def test_closed_prs_on_the_commit_do_not_matter(tmp_path: Path) -> None:
    other = {"number": 8, "state": "closed", "head": {"sha": HEAD}, "base": {"ref": "x"}}
    api = Api(others=[other])
    run = _publish(tmp_path, _artefact(tmp_path, _evaluation(after=0.0, status="pass")))
    assert run.conclusion == "success" and api.checks[0]["conclusion"] == "success"


@respx.mock
def test_huge_integer_is_refused_not_crashed(tmp_path: Path) -> None:
    Api()
    text = json.dumps(_evaluation()).replace(
        '"kg_co2e_yr_after": 150.0', '"kg_co2e_yr_after": 1' + "0" * 400
    )
    run = _publish(tmp_path, _artefact(tmp_path, text))
    assert run.status is None and run.conclusion == "failure"


@respx.mock
def test_acknowledgement_is_looked_up_by_the_publisher(tmp_path: Path) -> None:
    api = Api()
    api.accepted_by_alice()
    run = _publish(tmp_path, _artefact(tmp_path, _evaluation()))
    assert (run.status, run.conclusion, run.exit_code) == ("accepted", "success", 0)
    assert "alice" in api.checks[0]["output"]["summary"]


@pytest.mark.parametrize(
    ("change", "why"),
    [
        (lambda d: d.update(extra_field=1), "schema"),
        (lambda d: d["result"].update(status="accepted"), "acceptance"),
        (lambda d: d["result"].update(accepted_by="mallory", accepted_reason="x"), "acceptance"),
        (lambda d: d["result"].update(head_sha=OTHER), "head commit"),
        (lambda d: d.update(repo="someone/else"), "repository"),
        (lambda d: d["result"].update(pr_number=0), "pull request"),
        (lambda d: d.update(schema_version=2), "schema"),
    ],
)
@respx.mock
def test_invalid_evaluation_fails_closed_without_a_comment(tmp_path: Path, change, why) -> None:
    api = Api()
    doc = _evaluation(after=0.0, status="pass")
    change(doc)
    run = _publish(tmp_path, _artefact(tmp_path, doc))
    assert run.status is None and run.conclusion == "failure" and run.exit_code == 1
    assert why in (run.problem or "")
    assert api.comments == []
    assert api.checks[0]["conclusion"] == "failure"
    assert api.checks[0]["output"]["title"] == "evaluation unusable"


@respx.mock
def test_malformed_and_oversized_artefacts_are_refused(tmp_path: Path) -> None:
    Api()
    assert _publish(tmp_path / "a", _artefact(tmp_path / "a", "{not json")).conclusion == "failure"
    big = b"{" + b" " * (MAX_EVALUATION_BYTES + 1) + b"}"
    run = _publish(tmp_path / "b", _artefact(tmp_path / "b", big))
    assert "limit" in (run.problem or "")


@respx.mock
def test_exactly_one_evaluation_is_read(tmp_path: Path) -> None:
    Api()
    root = _artefact(tmp_path, _evaluation(), "run1")
    _artefact(tmp_path, _evaluation(after=0.0, status="pass"), "run2")
    run = _publish(tmp_path, root)
    assert "found 2" in (run.problem or "")
    empty = tmp_path / "empty"
    empty.mkdir()
    assert "found 0" in (_publish(tmp_path, empty).problem or "")


@respx.mock
def test_trusted_pr_number_must_match(tmp_path: Path) -> None:
    Api()
    run = _publish(tmp_path, _artefact(tmp_path, _evaluation()), pr=8)
    assert "pull request" in (run.problem or "")


@respx.mock
def test_pr_whose_head_moved_gets_nothing_published(tmp_path: Path) -> None:
    """A PR number from the artefact is only used when the API confirms its head is this commit;
    otherwise nothing is published, so a required check stays pending."""
    api = Api(pr_head=OTHER)
    api.accepted_by_alice()
    run = _publish(tmp_path, _artefact(tmp_path, _evaluation(after=0.0, status="pass")))
    assert run.status is None and run.exit_code == 0
    assert api.comments == [] and api.checks == []
    assert not api.labels.called  # acceptance was never looked up


@pytest.mark.parametrize(
    "files",
    [
        [{"filename": ".github/workflows/emissiongate-gate.yml", "status": "modified"}],
        [{"filename": ".github/workflows/other.yml", "status": "added"}],
        [{"filename": "x.yml", "previous_filename": ".github/actions/a/action.yml"}],
        [{"filename": f"f{i}.tf"} for i in range(1000)],
    ],
    ids=["edits-evaluate", "adds-workflow", "renames-action", "too-many-files"],
)
@respx.mock
def test_pr_that_can_rewrite_its_evaluate_job_fails_closed(tmp_path: Path, files) -> None:
    """A pull_request run uses the PR's own workflow files, so it could forge evaluation.json
    (here: an empty, "passing" one). The check fails and nothing is commented."""
    api = Api(files=files)
    run = _publish(tmp_path, _artefact(tmp_path, _evaluation(after=0.0, status="pass")))
    assert run.status is None and run.conclusion == "failure" and run.exit_code == 1
    assert api.comments == []
    assert api.checks[0]["output"]["title"] == "not trusted: workflow files changed"


@respx.mock
def test_policy_without_the_key_fails_not_evaluated(tmp_path: Path) -> None:
    api = Api()
    repo = _policy_repo(tmp_path, "  not_evaluated_conclusion: failure", "")
    doc = _evaluation(status="not_evaluated")
    run = _publish(tmp_path, _artefact(tmp_path, doc), config_repo=repo)
    assert (run.status, run.conclusion, run.exit_code) == ("not_evaluated", "failure", 1)
    assert "fails until it can be evaluated" in api.comments[0]


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('"kg_co2e_yr_after": 150.0', '"kg_co2e_yr_after": NaN'),
        ('"kg_co2e_yr_after": 150.0', '"kg_co2e_yr_after": Infinity'),
        ('"kg_co2e_yr_after": 150.0', '"kg_co2e_yr_after": 1e999'),
        ('"kg_co2e_yr_after": 150.0', '"kg_co2e_yr_after": -1000000.0'),
    ],
    ids=["nan", "infinity", "overflow", "cancelling-negative"],
)
@respx.mock
def test_non_finite_or_negative_figures_are_refused(tmp_path: Path, old: str, new: str) -> None:
    api = Api()
    text = json.dumps(_evaluation())
    assert old in text
    run = _publish(tmp_path, _artefact(tmp_path, text.replace(old, new)))
    assert run.status is None and run.conclusion == "failure"
    assert api.comments == []


@respx.mock
def test_comment_in_the_artefact_is_never_posted(tmp_path: Path) -> None:
    api = Api()
    root = _artefact(tmp_path, _evaluation())
    (root / "run1" / "comment.md").write_text(f"{MARKER}\n## Approved by security", "utf-8")
    _publish(tmp_path, root)
    assert "Approved by security" not in api.comments[0]


CODE_SPAN = re.compile(r"(?<![`\\])(`+)(?!`)(.+?)(?<!`)\1(?!`)")
EVIL = "x` [Security approved](https://evil.example) @org/admins <img src=x> `"


@respx.mock
def test_artefact_identifiers_and_keys_are_inert(tmp_path: Path) -> None:
    """ledger_run_id, base_sha, suggestion keys: all artefact strings, all escaped."""
    api = Api()
    doc = _evaluation()
    doc["result"]["ledger_run_id"] = EVIL
    doc["result"]["base_sha"] = EVIL
    doc["result"]["suggestions"] = [
        {
            "address": ADDR,
            "template": "schedule",
            "params": {EVIL: "0 8 * * MON-FRI"},
            "kg_co2e_yr_delta_vs_head": -10.0,
            "plan_ok": True,
            "diff": "+ x",
        }
    ]
    _publish(tmp_path, _artefact(tmp_path, doc))
    for body in (api.comments[0], api.checks[0]["output"]["summary"]):
        outside = CODE_SPAN.sub("", body)
        assert "<img" not in outside and "@org" not in outside
        assert "](https://evil" not in outside


@respx.mock
def test_energy_label_is_one_of_two_words(tmp_path: Path) -> None:
    Api()
    doc = _evaluation()
    doc["energy_wh"] = 1.0
    doc["energy_label"] = "measured\n::error::injected"
    run = _publish(tmp_path, _artefact(tmp_path, doc))
    assert run.status is None and "schema" in (run.problem or "")


@respx.mock
def test_check_summary_carries_provenance(tmp_path: Path) -> None:
    api = Api()
    run = _publish(tmp_path, _artefact(tmp_path, _evaluation()))
    summary = api.checks[0]["output"]["summary"]
    assert "Cloud Carbon Footprint" in summary and "`annual`" in summary
    assert run.run_dir.name in summary  # the publish ledger that holds the decision


@respx.mock
def test_untrusted_text_in_the_evaluation_is_escaped(tmp_path: Path) -> None:
    api = Api()
    doc = _evaluation(status="not_evaluated")
    doc["reason"] = "@org/admins <img src=x onerror=alert(1)> [click](https://evil.example)"
    doc["notes"] = ["<script>alert(1)</script>"]
    _publish(tmp_path, _artefact(tmp_path, doc))
    for body in (api.comments[0], api.checks[0]["output"]["summary"]):
        assert "<img" not in body and "<script>" not in body
        assert "@org" not in body and "](https://evil" not in body


@respx.mock
def test_check_api_error_is_ledgered_and_leaves_no_check(tmp_path: Path) -> None:
    Api(check_status=403)
    run = _publish(tmp_path, _artefact(tmp_path, _evaluation()))
    assert run.check_url is None
    events = Ledger(run.run_dir / "ledger.sqlite", "read", lambda: None).events()  # type: ignore[arg-type,return-value]
    assert any(e.kind == "fallback" and e.tool == "github.create_check_run" for e in events)


@respx.mock
def test_every_step_is_ledgered_with_the_artefact_digest(tmp_path: Path) -> None:
    Api()
    root = _artefact(tmp_path, _evaluation())
    digest = hashlib.sha256((root / "run1" / "evaluation.json").read_bytes()).hexdigest()
    run = _publish(tmp_path, root)
    events = Ledger(run.run_dir / "ledger.sqlite", "read", lambda: None).events()  # type: ignore[arg-type,return-value]
    tools = [e.tool for e in events if e.kind == "tool_call"]
    assert tools == [
        "artefact.read_evaluation",
        "github.pull",
        "github.commit_pulls",
        "github.pull_files",
        "github.acceptance",
        "github.upsert_comment",
        "github.create_check_run",
    ]
    read = next(e for e in events if e.tool == "artefact.read_evaluation")
    assert read.detail["sha256"] == digest
    assert events[-1].kind == "transition" and events[-1].detail["conclusion"] == "failure"
    assert "test-token-not-real" not in (run.run_dir / "ledger.sqlite").read_bytes().decode(
        "utf-8", "replace"
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _policy_repo(tmp: Path, old: str, new: str) -> Path:
    """A default-branch checkout whose .emissiongate/policy.yaml has `old` replaced by `new`."""
    repo = tmp / "trusted"
    (repo / ".emissiongate").mkdir(parents=True)
    policy = (ROOT / "policy.yaml").read_text(encoding="utf-8")
    assert old in policy
    (repo / ".emissiongate" / "policy.yaml").write_text(policy.replace(old, new), "utf-8")
    _git(repo, "init", "-b", "main", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "sec-test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "org policy")
    return repo


@respx.mock
def test_policy_comes_from_the_default_branch_checkout(tmp_path: Path) -> None:
    api = Api()
    repo = _policy_repo(tmp_path, "ack_kg_co2e_yr: 100.0", "ack_kg_co2e_yr: 1000.0")
    run = _publish(tmp_path, _artefact(tmp_path, _evaluation()), config_repo=repo)
    assert run.status == "pass_with_warning" and api.checks[0]["conclusion"] == "success"


def test_job_log_cannot_receive_workflow_commands(monkeypatch, capsys) -> None:
    """PR-controlled text printed in Actions is wrapped in stop-commands with a fresh token."""
    from emissiongate import cli

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    cli._print_untrusted("line\n::error title=Approved::forged\n")
    out = capsys.readouterr().out.splitlines()
    start = next(i for i, ln in enumerate(out) if ln.startswith("::stop-commands::"))
    token = out[start].split("::")[2]
    assert len(token) == 32
    end = out.index(f"::{token}::")
    assert start < out.index("::error title=Approved::forged") < end
