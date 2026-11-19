"""Publish step of the split gate (GATE §5, THREAT_MODEL B5). No LLM, no plan, no PR checkout.

The gate runs as two jobs. The evaluate job plans the pull request with no token and writes
`evaluation.json`. This step runs in a separate, privileged job (a `workflow_run` workflow whose
definition comes from the default branch). It never checks out or runs pull-request code, and it
treats the artefact as untrusted data:

- size-capped and validated against `GateEvaluation`, extra fields refused;
- bound to the trusted head SHA and repository from the event, never from the artefact;
- the PR number is checked against the API: the PR's head must be that SHA, or nothing at all is
  published (a required check stays pending);
- a `pull_request` run uses the PR's own workflow files, so a PR that changes anything under
  `.github/` could have forged its evaluation: the check fails closed (the publish workflow also
  requires `workflow_run.path` to be the evaluate workflow);
- NaN, Infinity and negative emissions figures are refused;
- the status is re-derived in `core.verdict` from the projections with this job's own policy, and an
  artefact can never carry an acceptance;
- the comment is re-rendered from the validated data (an artefact's `comment.md` is never read).

It records its own ledger (invariant 8) and publishes a check run named `CHECK_NAME` on the head
SHA, which is the check an organisation makes required. A missing or invalid artefact fails that
check, as a crashed single-job gate did (fail closed, invariant 6).
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from emissiongate.agents import reporter
from emissiongate.config import Settings
from emissiongate.contracts import GateEvaluation
from emissiongate.core.factors import FACTORS_FILE, Factors
from emissiongate.core.ledger import Ledger
from emissiongate.core.policy import Policy
from emissiongate.core.verdict import conclusion, verdict
from emissiongate.orchestrator.gate import accept, trusted_settings, upsert
from emissiongate.tools.github import GitHub, GitHubError

STATE = "PUBLISHING"
CHECK_NAME = "EmissionGate / carbon"  # part of the compatibility contract (ADR-0021)
MAX_EVALUATION_BYTES = 2_000_000
MAX_PR_FILES = 1000  # GitHub._paged reads at most 10 pages of 100
TRUSTED_ONLY = (".github/",)  # a PR that touches these could have rewritten the evaluate job
KG_FIELDS = (
    "kg_co2e_yr_before",
    "kg_co2e_yr_after",
    "kg_co2e_yr_after_low",
    "kg_co2e_yr_after_high",
    "kg_co2e_yr_before_low",
    "kg_co2e_yr_before_high",
)


def _head(pull: dict) -> str:
    return str((pull.get("head") or {}).get("sha") or "")


def _reject_constant(name: str) -> float:
    raise InvalidEvaluation(f"evaluation.json contains {name}")


def _bounded(text: str) -> int:
    if len(text.lstrip("-")) > 18:
        raise InvalidEvaluation("evaluation.json contains an out-of-range integer")
    return int(text)


def _finite(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise InvalidEvaluation("evaluation.json contains a non-finite number")
    return value


class InvalidEvaluation(ValueError):
    """The evaluate job's artefact is missing, malformed or not for this commit."""


@dataclass
class PublishRun:
    status: str | None  # None when the evaluation could not be used
    conclusion: str
    comment: str | None
    run_dir: Path
    exit_code: int
    url: str | None = None
    check_url: str | None = None
    problem: str | None = None


def find_evaluation(artefact: Path) -> Path:
    """The one `evaluation.json` in a downloaded artefact: a file, or a directory one level deep."""
    if artefact.is_file() and not artefact.is_symlink():
        candidates = [artefact]
    elif artefact.is_dir():
        candidates = sorted(artefact.glob("evaluation.json")) + sorted(
            artefact.glob("*/evaluation.json")
        )
    else:
        candidates = []
    if len(candidates) != 1:
        raise InvalidEvaluation(
            f"expected one evaluation.json in the artefact, found {len(candidates)}"
        )
    path = candidates[0]
    if path.is_symlink() or not path.is_file():
        raise InvalidEvaluation("evaluation.json is not a regular file")
    return path


def load_evaluation(path: Path) -> tuple[GateEvaluation, str, int]:
    """(evaluation, sha256 of the file, size in bytes); raises InvalidEvaluation."""
    size = path.stat().st_size
    if size > MAX_EVALUATION_BYTES:
        raise InvalidEvaluation(f"evaluation.json is {size} bytes (limit {MAX_EVALUATION_BYTES})")
    data = path.read_bytes()
    try:
        # NaN or Infinity makes every threshold comparison false, i.e. a pass (THREAT_MODEL B5).
        json.loads(data, parse_constant=_reject_constant, parse_float=_finite, parse_int=_bounded)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, InvalidEvaluation):
            raise
        raise InvalidEvaluation("evaluation.json is not valid JSON") from exc
    try:
        ev = GateEvaluation.model_validate_json(data)
    except ValidationError as exc:
        raise InvalidEvaluation(
            f"evaluation.json does not match the schema ({exc.error_count()} errors)"
        ) from exc
    r = ev.result
    if r.status == "accepted" or r.accepted_by is not None or r.accepted_reason is not None:
        raise InvalidEvaluation("an evaluation cannot carry an acceptance")
    for p in r.projections:
        if any((getattr(p, f) or 0.0) < 0 for f in KG_FIELDS):
            raise InvalidEvaluation("evaluation has a negative emissions figure")
    return ev, hashlib.sha256(data).hexdigest(), size


class Publisher:
    def __init__(
        self,
        settings: Settings,
        artefact: Path,
        repo: str,
        head_sha: str,
        github: GitHub,
        base_branch: str,
        pr: int = 0,
        config_repo: Path | None = None,
        config_ref: str = "HEAD",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.s = settings
        self.artefact = artefact
        self.repo, self.head_sha, self.github, self.pr = repo, head_sha, github, pr
        self.base_branch = base_branch
        self._pr_pull: dict | None = None
        self.config_repo, self.config_ref = config_repo, config_ref
        self.clock = clock

    def run(self) -> PublishRun:
        with tempfile.TemporaryDirectory(prefix="eg-publish-") as tmp:
            return self._run(Path(tmp))

    def _bind(self, ev: GateEvaluation) -> None:
        r = ev.result
        if ev.repo != self.repo:
            raise InvalidEvaluation("evaluation is for a different repository")
        if r.head_sha != self.head_sha:
            raise InvalidEvaluation("evaluation is for a different head commit")
        if r.pr_number <= 0:
            raise InvalidEvaluation("evaluation has no pull request number")
        if self.pr and r.pr_number != self.pr:
            raise InvalidEvaluation("evaluation is for a different pull request")

    def _check(
        self, ledger: Ledger, outcome: str, title: str, summary: str, state: str
    ) -> str | None:
        try:
            url = self.github.create_check_run(self.head_sha, CHECK_NAME, outcome, title, summary)
        except GitHubError as exc:
            # No check run: a required check stays pending, so the PR stays blocked (fail closed).
            ledger.append(
                state=state,
                kind="fallback",
                agent="reporter",
                tool="github.create_check_run",
                detail={"reason": str(exc)[:300], "conclusion": outcome},
            )
            return None
        ledger.append(
            state=state,
            kind="tool_call",
            agent="reporter",
            tool="github.create_check_run",
            detail={"head_sha": self.head_sha, "conclusion": outcome},
        )
        return url

    def _pull(self, ledger: Ledger, pr: int) -> dict | None:
        """The pull request, or None when the API call fails (ledgered either way)."""
        try:
            pull = self.github.pull(pr)
        except GitHubError as exc:
            ledger.append(
                state=STATE,
                kind="fallback",
                agent="reporter",
                tool="github.pull",
                detail={"pr": pr, "reason": str(exc)[:300]},
            )
            return None
        ledger.append(
            state=STATE,
            kind="tool_call",
            agent="reporter",
            tool="github.pull",
            detail={
                "pr": pr,
                "head_matches": _head(pull) == self.head_sha,
                "base_ref": str((pull.get("base") or {}).get("ref") or "")[:100],
            },
        )
        return pull

    def _files_problem(self, ledger: Ledger, pr: int) -> str | None:
        """Why PR `pr` could have rewritten its evaluate job (it changes `.github/`), or None."""
        try:
            files = self.github.pull_files(pr)
        except GitHubError as exc:
            ledger.append(
                state=STATE,
                kind="fallback",
                agent="reporter",
                tool="github.pull_files",
                detail={"pr": pr, "reason": str(exc)[:300]},
            )
            return f"could not list the files of #{pr} to confirm its workflows are unchanged"
        names = {n for f in files for n in (f.get("filename"), f.get("previous_filename")) if n}
        hits = sorted(n for n in names if n.startswith(TRUSTED_ONLY))
        ledger.append(
            state=STATE,
            kind="tool_call",
            agent="reporter",
            tool="github.pull_files",
            detail={"pr": pr, "files": len(files), "trusted_paths_changed": len(hits)},
        )
        if len(files) >= MAX_PR_FILES:
            return f"#{pr} changes {len(files)}+ files; its workflows cannot be confirmed"
        if hits:
            return f"#{pr} changes " + ", ".join(hits[:5])
        return None

    def _untrusted(self, ledger: Ledger, pr: int) -> str | None:
        """Why the check on this commit cannot be trusted, or None (THREAT_MODEL B5).

        A check run belongs to a commit, not a pull request, so every open PR whose head is this
        commit must target the default branch and leave `.github/` unchanged: otherwise another
        PR's run (with another base, or its own workflow files) could write the latest check.
        """
        others: list[int] = []
        try:
            listed = self.github.commit_pulls(self.head_sha)
        except GitHubError as exc:
            ledger.append(
                state=STATE,
                kind="fallback",
                agent="reporter",
                tool="github.commit_pulls",
                detail={"reason": str(exc)[:300]},
            )
            return "could not list the pull requests on this commit"
        for item in listed:
            number = item.get("number")
            if (
                isinstance(number, int)
                and number != pr
                and item.get("state") == "open"
                and _head(item) == self.head_sha
            ):
                others.append(number)
        ledger.append(
            state=STATE,
            kind="tool_call",
            agent="reporter",
            tool="github.commit_pulls",
            detail={"listed": len(listed), "other_open_prs": len(others)},
        )
        for number in [pr, *sorted(others)]:
            pull = self._pr_pull if number == pr else self._pull(ledger, number)
            if pull is None:
                return f"could not read #{number}"
            base = str((pull.get("base") or {}).get("ref") or "")
            if base != self.base_branch:
                return f"#{number} targets {base[:100]!r}, not the default branch"
            problem = self._files_problem(ledger, number)
            if problem:
                return problem
        return None

    def _run(self, tmp: Path) -> PublishRun:
        started = self.clock()
        run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}-publish-{self.head_sha[:12]}"
        run_dir = self.s.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        ledger = Ledger(run_dir / "ledger.sqlite", run_id, self.clock)
        if self.config_repo is not None:
            s, sources = trusted_settings(self.s, self.config_repo, self.config_ref, tmp, ledger)
        else:
            s = self.s
            sources = {"policy": str(s.policy_path), "suppressions": str(s.suppressions_path)}
        ledger.append(
            state=STATE,
            kind="transition",
            detail={
                "repo": self.repo,
                "head_sha": self.head_sha,
                "pr": self.pr,
                "ci": s.ci,
                "policy_source": sources["policy"],
                "suppressions_source": sources["suppressions"],
            },
        )
        policy = Policy.from_docs(s.policy(), s.suppressions())
        factors = Factors.load(s.factors_dir / FACTORS_FILE)
        try:
            path = find_evaluation(self.artefact)
            ev, digest, size = load_evaluation(path)
            self._bind(ev)
        except InvalidEvaluation as exc:
            ledger.append(
                state="REFUSED",
                kind="error",
                agent="reporter",
                payload={"problem": str(exc)},
                detail={"invalid_evaluation": True, "problem": str(exc)[:300]},
            )
            title, summary = reporter.check_unusable()
            check_url = self._check(ledger, "failure", title, summary, "REFUSED")
            ledger.close()
            return PublishRun(None, "failure", None, run_dir, 1, None, check_url, str(exc))
        evidence = ledger.append(
            state=STATE,
            kind="tool_call",
            agent="reporter",
            tool="artefact.read_evaluation",
            detail={
                "sha256": digest,
                "bytes": size,
                "evaluation_run_id": ev.result.ledger_run_id,
                "pr": ev.result.pr_number,
            },
        )
        pr = ev.result.pr_number
        self._pr_pull = self._pull(ledger, pr)
        if self._pr_pull is None or _head(self._pr_pull) != self.head_sha:
            # Stale (a newer push has its own run) or unconfirmable: publish nothing, so a required
            # check stays pending rather than trusting an evaluation tied to no confirmed PR.
            ledger.append(
                state="STALE",
                kind="transition",
                detail={"pr": pr, "published": False},
            )
            ledger.close()
            return PublishRun(
                None, "none", None, run_dir, 0, problem="pull request head not confirmed"
            )
        touched = self._untrusted(ledger, pr)
        if touched:
            # A pull_request run uses the PR's own workflow files (and the check is per commit).
            ledger.append(
                state="REFUSED",
                kind="error",
                agent="reporter",
                detail={"untrusted_workflow": True, "problem": touched[:300]},
            )
            title, summary = reporter.check_untrusted_workflow(touched)
            check_url = self._check(ledger, "failure", title, summary, "REFUSED")
            ledger.close()
            return PublishRun(None, "failure", None, run_dir, 1, None, check_url, touched)
        gate_cfg = policy.gate
        prior = "not_evaluated" if ev.result.status == "not_evaluated" else "pass"
        try:
            status, why, totals = verdict(prior, list(ev.result.projections), gate_cfg)
            conclusion(status, gate_cfg)  # an invalid policy value fails here, not later
        except ValueError as exc:
            ledger.append(
                state="REFUSED",
                kind="error",
                agent="reporter",
                detail={"verdict_error": True, "problem": str(exc)[:300]},
            )
            title, summary = reporter.check_unusable()
            check_url = self._check(ledger, "failure", title, summary, "REFUSED")
            ledger.close()
            return PublishRun(None, "failure", None, run_dir, 1, None, check_url, str(exc))
        reason = ev.reason or why
        result = ev.result.model_copy(
            update={
                "status": status,
                "net_kg_co2e_yr": totals.net,
                "net_kg_co2e_yr_low": totals.low,
                "net_kg_co2e_yr_high": totals.high,
            }
        )
        if status == "ack_required":
            by, why_accepted = accept(
                ledger, self.github, pr, gate_cfg["ack_label"], self.head_sha, totals.net, STATE
            )
            if by:
                status = "accepted"
                result = result.model_copy(
                    update={"status": status, "accepted_by": by, "accepted_reason": why_accepted}
                )
        comment = None
        if ev.comment:
            comment = reporter.gate_comment(
                result,
                gate_cfg,
                factors,
                int(policy.thresholds["lookback_days"]),
                ev.runtime_s,
                ev.energy_wh,
                ev.energy_label,
                reason,
                ev.notes,
                publish_run_id=run_id,
            )
            (run_dir / "comment.md").write_text(comment, encoding="utf-8", newline="\n")
        (run_dir / "gate_result.json").write_text(
            result.model_dump_json(indent=1), encoding="utf-8"
        )
        url = None
        if comment:
            url = upsert(ledger, self.github, pr, comment, status.upper())
        outcome = conclusion(status, gate_cfg)
        title, summary = reporter.check_output(
            result, gate_cfg, reason, factors.source, run_id, evidence.seq
        )
        check_url = self._check(ledger, outcome, title, summary, status.upper())
        ledger.append(
            state=status.upper(),
            kind="transition",
            detail={
                "status": status,
                "conclusion": outcome,
                "net_kg_co2e_yr": totals.net,
                "low": totals.low,
                "high": totals.high,
            },
        )
        ledger.close()
        exit_code = 1 if outcome == "failure" else 0
        return PublishRun(status, outcome, comment, run_dir, exit_code, url, check_url)
