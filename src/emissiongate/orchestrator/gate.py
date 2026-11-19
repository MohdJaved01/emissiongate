"""PR gate (GATE.md, ADR-0015): carbon delta of one pull request, before merge. No LLM in CI.

The gate informs; humans decide (AGENTS.md invariant 14). It plans base and head offline, projects
energy per changed resource, posts one sticky comment with validated suggestions, and fails the job
only at `policy.yaml -> gate.ack_kg_co2e_yr` unless a human added the acknowledgement label with a
reason for the current head commit. It never pushes, approves or merges. A GitHub error never
changes the job result; it is ledgered and the comment stays in the job log.
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from emissiongate.agents import diff_collector, reporter
from emissiongate.agents.diff_collector import Unit
from emissiongate.config import Settings, UntrustedInput, check_trusted
from emissiongate.contracts import GatePrediction, GateResult, GateSuggestion, Projection, Resource
from emissiongate.core import energy, hcl, patches, safety
from emissiongate.core import projection as pj
from emissiongate.core.factors import FACTORS_FILE, FactorNotFound, Factors
from emissiongate.core.ledger import Ledger
from emissiongate.core.policy import Policy
from emissiongate.core.regions import region_time_zone
from emissiongate.core.utilisation import summarise
from emissiongate.orchestrator.budget import Budget, BudgetExceeded
from emissiongate.orchestrator.measure import Tracker
from emissiongate.tools import gitrefs, metrics, tf
from emissiongate.tools.github import GitHub, GitHubError

STATE = "EVALUATING"


@dataclass
class GateRun:
    result: GateResult
    comment: str | None
    run_dir: Path
    exit_code: int
    url: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class _Ctx:
    ledger: Ledger
    budget: Budget
    policy: Policy
    factors: Factors
    prices: dict
    notes: list[str] = field(default_factory=list)


def _state(u: Unit | None) -> pj.UnitState | None:
    if u is None or not u.instance_type or not u.region:
        return None
    return pj.UnitState(u.instance_type, u.count, u.region, u.hours_per_year)


def _not_quantified(address: str, reason: str) -> Projection:
    return Projection(
        address=address,
        basis="assumed",
        kg_co2e_yr_before=0.0,
        kg_co2e_yr_after=0.0,
        kwh_yr_delta=0.0,
        usd_synthetic_yr_delta=0.0,
        provenance=[],
        quantified=False,
        reason=reason,
    )


def _short(side: str, error: str) -> str:
    """First OpenTofu `Error:` lines, for the comment (the full tail is in the ledger)."""
    errors = [ln.strip() for ln in error.splitlines() if ln.strip().startswith("Error:")]
    first = next((ln.strip() for ln in error.splitlines() if ln.strip()), "")
    detail = "; ".join(dict.fromkeys(errors)) or first
    return f"the {side} configuration does not plan ({detail[:300]})"


def _find_file(head_dir: Path, tf_type: str, name: str) -> str | None:
    for path in sorted(head_dir.glob("*.tf")):
        if (tf_type, name) in hcl.block_names(path.read_text(encoding="utf-8"), "resource"):
            return path.name
    return None


def _ledger_history(c: _Ctx, ws: tf.Workspace, start: int, agent: str, **detail: object) -> int:
    for cmd in ws.history[start:]:
        c.ledger.append(
            state=STATE,
            kind="tool_call",
            agent=agent,
            tool=f"tofu.{cmd.args[0]}",
            duration_ms=cmd.duration_ms,
            detail={"exit_code": cmd.exit_code, **detail},  # type: ignore[dict-item]
        )
    return len(ws.history)


def _observed(c: _Ctx, data_dir: Path, name: str) -> pj.Observed | None:
    rid = name.replace("_", "-")
    tel = metrics.load(data_dir / "metrics", rid)
    c.ledger.append(
        state=STATE,
        kind="tool_call",
        agent="diff_collector",
        tool="metrics.load",
        detail={"resource_id": rid, "found": tel is not None},
    )
    if tel is None or tel.get("cpu") is None:
        return None
    th = c.policy.thresholds
    util = summarise(
        name,
        tel["start"],
        tel["running"],
        tel["cpu"],
        tel.get("gpu"),
        tel.get("requests"),
        th["lookback_days"],
        th["min_datapoints"],
        th["idle_cpu_p95"],
    )
    if not util.sufficient or util.cpu_avg is None:
        return None
    return pj.Observed(util.cpu_avg, util.gpu_avg, util.cpu_p95)


def _storage_projection(c: _Ctx, addr: str, b: Unit | None, h: Unit | None) -> Projection:
    storage_prices = c.prices.get("storage_usd_per_gb_month_synthetic", {})

    def side(u: Unit | None) -> tuple[float, float, float, tuple]:
        if u is None:
            return 0.0, 0.0, 0.0, ()
        if u.storage_gb is None or u.storage_type is None or not u.region:
            raise ValueError("volume size, type or region unknown")
        if u.storage_type not in storage_prices:
            raise ValueError(f"no synthetic price for storage class {u.storage_type}")
        gb = u.storage_gb * u.count
        s = energy.storage(c.factors, gb / 1000.0, u.storage_type)
        i = c.factors.region_g_per_kwh(u.region)
        usd = gb * storage_prices[u.storage_type] * 12
        return s.kwh, energy.kg_co2e(s.kwh, i.value), usd, (*s.provenance, i.provenance)

    try:
        bk, bg, bu, bp = side(b)
        hk, hg, hu, hp = side(h)
    except (FactorNotFound, ValueError) as exc:
        return _not_quantified(addr, str(exc))
    return Projection(
        address=addr,
        basis="observed",
        kg_co2e_yr_before=bg,
        kg_co2e_yr_after=hg,
        kwh_yr_delta=hk - bk,
        usd_synthetic_yr_delta=hu - bu,
        provenance=list(dict.fromkeys(hp or bp)),
    )


def _solve_u(factors: Factors, state: pj.UnitState, kg_target: float, u_gpu: float | None) -> float:
    """Recover the head utilisation the projection used (energy is linear in u)."""
    e0 = pj.energy_kg(factors, state, 0.0, u_gpu).kg
    e1 = pj.energy_kg(factors, state, 1.0, u_gpu).kg
    if e1 == e0:
        return 0.0
    return max(0.0, min(1.0, (kg_target - e0) / (e1 - e0)))


class Gate:
    def __init__(
        self,
        settings: Settings,
        estate_dir: Path,
        base: str,
        head: str,
        pr: int = 0,
        repo: str = "",
        github: GitHub | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        config_from_base: bool = False,
    ) -> None:
        self.s = settings
        self.estate_dir = estate_dir
        self.base_ref, self.head_ref = base, head
        self.pr, self.repo, self.github, self.clock = pr, repo, github, clock
        self.config_from_base = config_from_base

    def _trusted_settings(self, tmp: Path, ledger: Ledger) -> tuple[Settings, dict[str, str]]:
        """Settings with policy and suppressions from trusted sources only (THREAT_MODEL B2).

        With `config_from_base`, `.emissiongate/policy.yaml` and `.emissiongate/suppressions.yaml`
        are read from the base commit's tree (never the head's), when present; otherwise the
        configured files apply. Every git read is ledgered (invariant 8).
        """
        s = self.s
        sources = {"policy": str(s.policy_path), "suppressions": str(s.suppressions_path)}
        if not self.config_from_base:
            return s, sources
        base_sha = gitrefs.rev_parse(self.estate_dir, self.base_ref)
        ledger.append(
            state=STATE,
            kind="tool_call",
            agent="diff_collector",
            tool="git.rev_parse",
            detail={"ref": self.base_ref, "sha": base_sha},
        )
        trusted = tmp / "trusted-config"
        trusted.mkdir()
        updates: dict[str, Path] = {}
        for key, name in (("policy", "policy.yaml"), ("suppressions", "suppressions.yaml")):
            path = f".emissiongate/{name}"
            blob = gitrefs.read_blob(self.estate_dir, base_sha, path)
            ledger.append(
                state=STATE,
                kind="tool_call",
                agent="diff_collector",
                tool="git.read_blob",
                detail={"sha": base_sha, "path": path, "found": blob is not None},
            )
            if blob is not None:
                (trusted / name).write_bytes(blob)
                updates[f"{key}_path"] = trusted / name
                sources[key] = f"base:{base_sha}:{path}"
        return dataclasses.replace(s, **updates), sources

    def run(self) -> GateRun:
        with tempfile.TemporaryDirectory(prefix="eg-gate-") as tmp:
            return self._run(Path(tmp))

    def _open_ledger(self, run_id: str) -> tuple[Path, Ledger]:
        """The run's ledger, opened before anything else so a refusal is recorded too.

        In CI a configured path inside the PR's checkout refuses the run (THREAT_MODEL B2). The
        refusal is ledgered unless the runs directory itself is the untrusted path, in which case
        nothing is written there at all.
        """
        untrusted = check_trusted(self.s, self.estate_dir) if self.s.ci else []
        if any(u.startswith("runs_dir ") for u in untrusted):
            raise UntrustedInput("; ".join(untrusted))
        run_dir = self.s.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        ledger = Ledger(run_dir / "ledger.sqlite", run_id, self.clock)
        if untrusted:
            ledger.append(
                state="REFUSED",
                kind="error",
                payload={"untrusted_inputs": untrusted},
                detail={"untrusted_inputs": len(untrusted), "ci": True},
            )
            ledger.close()
            raise UntrustedInput("; ".join(untrusted))
        return run_dir, ledger

    def _run(self, tmp: Path) -> GateRun:
        started = self.clock()
        t0 = time.monotonic()
        run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}-gate-pr{self.pr}"
        run_dir, ledger = self._open_ledger(run_id)
        s, config_sources = self._trusted_settings(tmp, ledger)
        tracker = Tracker(s.country_iso)
        tracker.start()
        policy = Policy.from_docs(s.policy(), s.suppressions())
        prices_path = s.data_dir / "prices_synthetic.json"
        prices = json.loads(prices_path.read_text(encoding="utf-8")) if prices_path.exists() else {}
        c = _Ctx(
            ledger=ledger,
            budget=Budget(policy.ceilings),
            policy=policy,
            factors=Factors.load(s.factors_dir / FACTORS_FILE),
            prices=prices,
        )
        # In CI the tofu data directory is per run and outside the checkout (THREAT_MODEL B2, B3).
        tofu_data = tmp / "tofu-data" if s.ci else s.cwd / ".eg-cache" / "tofu-data"
        cfg = tf.TofuConfig(bin=s.tofu_bin, plugin_dir=s.tofu_plugin_dir, data_dir=tofu_data)
        c.ledger.append(
            state=STATE,
            kind="transition",
            detail={
                "pr": self.pr,
                "repo": self.repo,
                "base": self.base_ref,
                "head": self.head_ref,
                "ci": s.ci,
                "policy_source": config_sources["policy"],
                "suppressions_source": config_sources["suppressions"],
            },
        )
        base_dir, head_dir = tmp / "base", tmp / "head"
        base_tree = gitrefs.export_tree(self.estate_dir, self.base_ref, base_dir)
        head_tree = gitrefs.export_tree(self.estate_dir, self.head_ref, head_dir)
        base_sha, head_sha = base_tree.sha, head_tree.sha
        for side, tree in (("base", base_tree), ("head", head_tree)):
            c.ledger.append(
                state=STATE,
                kind="tool_call",
                agent="diff_collector",
                tool="git.export_tree",
                detail={"side": side, "sha": tree.sha, "files": len(tree.files)},
            )
        finish = self._finisher(c, run_dir, tracker, t0, started, base_sha, head_sha)

        # Refused tree entries (symlinks, submodules) and every file OpenTofu loads, in every
        # directory, go through the screen (THREAT_MODEL B1).
        unsafe = [
            f"{side}/{p}"
            for side, tree in (("base", base_tree), ("head", head_tree))
            for p in tree.refused
        ] + [
            f"{side}/{p}"
            for side, d, tree in (("base", base_dir, base_tree), ("head", head_dir, head_tree))
            for p in safety.problems(
                {
                    f: (d / f).read_text(encoding="utf-8", errors="replace")
                    for f in tree.files
                    if safety.loaded_by_tofu(f)
                }
            )
        ]
        if unsafe:
            c.ledger.append(
                state=STATE,
                kind="decision",
                agent="diff_collector",
                payload={"problems": unsafe},
                detail={"not_planned": True, "problems": len(unsafe)},
            )
            reason = "configuration not planned for safety: " + "; ".join(unsafe[:3])
            return finish("not_evaluated", [], [], [], reason=reason)

        views: dict[str, diff_collector.PlanView] = {}
        with tf.Workspace(cfg, base_dir) as ws_base, tf.Workspace(cfg, head_dir) as ws_head:
            for side, ws in (("base", ws_base), ("head", ws_head)):
                error: str | None = None
                plan = None
                try:
                    c.budget.check()
                    result, plan = ws.plan_json()
                    if plan is None:
                        error = result.stderr_tail
                except tf.TofuError as exc:
                    error = str(exc)
                except BudgetExceeded as exc:
                    return finish("not_evaluated", [], [], [], reason=f"ceiling {exc.ceiling}")
                _ledger_history(c, ws, 0, "diff_collector", side=side)
                if plan is None:
                    c.ledger.append(
                        state=STATE,
                        kind="error",
                        agent="diff_collector",
                        payload={"side": side, "stderr_tail": error or ""},
                        detail={"side": side, "plan_failed": True},
                    )
                    return finish(
                        "not_evaluated", [], [], [], reason=_short(side, error or "plan failed")
                    )
                views[side] = diff_collector.read_plan(plan)
            changes = diff_collector.pair(views["base"], views["head"])
            relevant = [ch for ch in changes if ch.carbon_relevant]
            if not relevant:
                # Coverage stays visible: no comment only when nothing changed at all (E1).
                seen = any(ch.change != "unchanged" for ch in changes)
                return finish("pass", changes, [], [], no_comment=not seen)
            projections: list[Projection] = []
            observed: dict[str, pj.Observed | None] = {}
            gate_cfg = policy.gate
            for ch in relevant:
                b = views["base"].units.get(ch.address)
                h = views["head"].units.get(ch.address)
                unit = h or b
                assert unit is not None
                gaps = sorted({*(b.missing if b else ()), *(h.missing if h else ())})
                if gaps or not unit.region:
                    reason = "unknown: " + ", ".join(gaps or ["region"])
                    projections.append(_not_quantified(ch.address, reason))
                    continue
                if unit.tf_type in diff_collector.STORAGE_TYPES:
                    projections.append(_storage_projection(c, ch.address, b, h))
                    continue
                obs = _observed(c, s.data_dir, unit.name) if b is not None else None
                observed[ch.address] = obs
                projections.append(
                    pj.project(
                        ch.address,
                        _state(b),
                        _state(h),
                        obs,
                        c.factors,
                        gate_cfg,
                        c.prices.get("instance_usd_per_hour_synthetic"),
                    )
                )
            event = c.ledger.append(
                state=STATE,
                kind="decision",
                agent="quantifier",
                payload=[p.model_dump(mode="json") for p in projections],
                detail={"projections": len(projections), "tier": "annual"},
            )
            self._projection_event = event.seq
            try:
                suggestions = self._suggest(
                    c, ws_head, head_dir, views["head"], projections, observed
                )
            except BudgetExceeded as exc:
                c.notes.append(f"suggestions stopped at ceiling {exc.ceiling}")
                suggestions = []
        return finish("pass", changes, projections, suggestions)

    # ---- suggestions -----------------------------------------------------------------------

    def _suggest(
        self,
        c: _Ctx,
        ws: tf.Workspace,
        head_dir: Path,
        head: diff_collector.PlanView,
        projections: list[Projection],
        observed: dict[str, pj.Observed | None],
    ) -> list[GateSuggestion]:
        gate_cfg = c.policy.gate
        factors = c.factors
        lo_u, hi_u = (float(x) for x in gate_cfg["assumed_utilisation_band"])
        on_cron, off_cron = gate_cfg["assumed_schedule"]
        out: list[GateSuggestion] = []
        for p in sorted(projections, key=lambda x: x.kg_co2e_yr_before - x.kg_co2e_yr_after):
            if not p.quantified or p.kg_co2e_yr_after <= p.kg_co2e_yr_before:
                continue
            unit = head.units.get(p.address)
            if unit is None or unit.tf_type != "aws_autoscaling_group" or not unit.instance_type:
                continue
            file = _find_file(head_dir, unit.tf_type, unit.name)
            if file is None or unit.region is None:
                continue
            obs = observed.get(p.address)
            head_state = pj.UnitState(
                unit.instance_type, unit.count, unit.region, unit.hours_per_year
            )
            if obs is None:
                u_cpu = factors.constant("default_cpu_utilization").value
                u_gpu: float | None = float(gate_cfg["assumed_gpu_utilisation"])
            else:
                u_gpu = obs.u_gpu
                u_cpu = _solve_u(factors, head_state, p.kg_co2e_yr_after, u_gpu)
            text = (head_dir / file).read_text(encoding="utf-8")
            resource = Resource(
                resource_id=unit.name.replace("_", "-"),
                kind="ec2_asg",
                region=unit.region,
                instance_type=unit.instance_type,
                count=unit.count,
                tags=unit.tags,
                tf_file=file,
                tf_address=unit.address,
            )
            spec = factors.instance(unit.instance_type).value
            options: list[tuple[str, dict[str, str], pj.UnitState, float]] = []
            if spec.arch == "x86_64" and not spec.gpu_count:
                for t in factors.instance_types():
                    alt = factors.instance(t).value
                    if (
                        alt.arch == "arm64"
                        and alt.family[0] == spec.family[0]
                        and (alt.size == spec.size)
                    ):
                        state = pj.UnitState(t, unit.count, unit.region, unit.hours_per_year)
                        params = {"target_instance_type": t, "image_param": "ami_arm64"}
                        options.append(("graviton", params, state, u_cpu))
                        break
            if not unit.schedules and c.policy.schedule_allowed(unit.tags):
                hours = pj.hours_per_year([(on_cron, "", 1), (off_cron, "", 0)])
                params = {
                    "on_cron": on_cron,
                    "off_cron": off_cron,
                    "time_zone": region_time_zone(unit.region),
                    "min_on": str(unit.count),
                }
                state = pj.UnitState(unit.instance_type, unit.count, unit.region, hours)
                options.append(("schedule", params, state, u_cpu))
            max_p95 = float(c.policy.thresholds["rightsize_target_p95_max"])
            p95 = obs.p95_cpu if obs and obs.p95_cpu is not None else u_cpu
            for t in sorted(factors.instance_types(), key=lambda x: factors.instance(x).value.vcpu):
                alt = factors.instance(t).value
                if (
                    alt.family == spec.family
                    and alt.vcpu < spec.vcpu
                    and alt.gpu == spec.gpu
                    and p95 * spec.vcpu / alt.vcpu <= max_p95
                ):
                    state = pj.UnitState(t, unit.count, unit.region, unit.hours_per_year)
                    u_new = min(1.0, u_cpu * spec.vcpu / alt.vcpu)
                    options.append(("rightsize", {"target_instance_type": t}, state, u_new))
                    break
            for template, params, state, u in options:
                c.budget.check()
                try:
                    files = patches.render(template, resource, text, params)  # type: ignore[arg-type]
                except (patches.PatchError, KeyError, ValueError) as exc:
                    c.ledger.append(
                        state=STATE,
                        kind="fallback",
                        agent="strategist",
                        detail={"suggestion": template, "reason": str(exc)[:200]},
                    )
                    continue
                start = len(ws.history)
                result = ws.check(files)
                _ledger_history(c, ws, start, "validator", suggestion=template)
                if not result.ok:
                    c.ledger.append(
                        state=STATE,
                        kind="fallback",
                        agent="validator",
                        payload={"stderr_tail": result.stderr_tail},
                        detail={"suggestion": template, "reason": "plan failed; dropped"},
                    )
                    continue
                kg = pj.energy_kg(factors, state, u, u_gpu).kg
                delta = kg - p.kg_co2e_yr_after
                low = high = None
                basis = p.basis
                if p.basis == "assumed":
                    # same assumption band on both sides (head and suggestion)
                    low = pj.energy_kg(factors, state, lo_u, lo_u).kg - (
                        p.kg_co2e_yr_after_low or 0.0
                    )
                    high = pj.energy_kg(factors, state, hi_u, hi_u).kg - (
                        p.kg_co2e_yr_after_high or 0.0
                    )
                event = c.ledger.append(
                    state=STATE,
                    kind="decision",
                    agent="strategist",
                    payload={
                        "suggestion": template,
                        "params": params,
                        "delta": delta,
                        "low": low,
                        "high": high,
                        "basis": basis,
                    },
                    detail={
                        "address": p.address,
                        "suggestion": template,
                        "kg_co2e_yr_delta_vs_head": delta,
                    },
                )
                out.append(
                    GateSuggestion(
                        address=p.address,
                        template=template,  # type: ignore[arg-type]
                        params=params,
                        kg_co2e_yr_delta_vs_head=delta,
                        plan_ok=True,
                        diff=_diff(file, text, files[file]),
                        basis=basis,
                        kg_co2e_yr_delta_low=low,
                        kg_co2e_yr_delta_high=high,
                        ledger_event_id=event.seq,
                    )
                )
        out.sort(key=lambda g: g.kg_co2e_yr_delta_vs_head)
        keep = int(gate_cfg["max_suggestions"])
        return [g for g in out if g.kg_co2e_yr_delta_vs_head < 0][:keep]

    # ---- result ----------------------------------------------------------------------------

    def _finisher(
        self,
        c: _Ctx,
        run_dir: Path,
        tracker: Tracker,
        t0: float,
        started: datetime,
        base_sha: str,
        head_sha: str,
    ) -> Callable[..., GateRun]:
        def finish(
            status: str,
            changes: list,
            projections: list[Projection],
            suggestions: list[GateSuggestion],
            reason: str | None = None,
            no_comment: bool = False,
        ) -> GateRun:
            return self._finish(
                c,
                run_dir,
                tracker,
                t0,
                started,
                base_sha,
                head_sha,
                status,
                changes,
                projections,
                suggestions,
                reason,
                no_comment,
            )

        return finish

    def _finish(
        self,
        c: _Ctx,
        run_dir: Path,
        tracker: Tracker,
        t0: float,
        started: datetime,
        base_sha: str,
        head_sha: str,
        status: str,
        changes: list,
        projections: list[Projection],
        suggestions: list[GateSuggestion],
        reason: str | None,
        no_comment: bool,
    ) -> GateRun:
        gate_cfg = c.policy.gate
        q = [p for p in projections if p.quantified]

        def side(p: Projection, which: str) -> tuple[float, float]:
            after = getattr(p, f"kg_co2e_yr_after_{which}")
            before = getattr(p, f"kg_co2e_yr_before_{which}")
            a = p.kg_co2e_yr_after if after is None else after
            b = p.kg_co2e_yr_before if before is None else before
            return a, b

        net = sum(p.kg_co2e_yr_after - p.kg_co2e_yr_before for p in q)
        low = sum(a - b for a, b in (side(p, "low") for p in q))
        high = sum(a - b for a, b in (side(p, "high") for p in q))
        low, high = min(low, high), max(low, high)
        if status == "pass" and projections:
            if not q:
                status, reason = "not_evaluated", "nothing quantifiable"
            elif net >= float(gate_cfg["ack_kg_co2e_yr"]):
                status = "ack_required"
            elif net >= float(gate_cfg["warn_kg_co2e_yr"]):
                status = "pass_with_warning"
        accepted_by = accepted_reason = None
        if status == "ack_required" and self.github is not None and self.pr:
            try:
                accepted_by, accepted_reason = self.github.acceptance(
                    self.pr, gate_cfg["ack_label"], head_sha=head_sha
                )
                c.ledger.append(
                    state=STATE,
                    kind="tool_call",
                    agent="reporter",
                    tool="github.acceptance",
                    detail={
                        "label": gate_cfg["ack_label"],
                        "head_sha": head_sha,
                        "found": bool(accepted_by),
                        "reason_found": bool(accepted_reason),
                    },
                )
            except GitHubError as exc:
                c.ledger.append(
                    state=STATE,
                    kind="fallback",
                    agent="reporter",
                    tool="github.acceptance",
                    detail={"reason": str(exc)[:300]},
                )
            if accepted_by and accepted_reason:
                status = "accepted"
                c.ledger.append(
                    state="ACCEPTED",
                    kind="human_gate",
                    detail={
                        "gate": "carbon acknowledgement",
                        "accepted_by": accepted_by,
                        "reason": accepted_reason[:500],
                        "head_sha": head_sha,
                        "net_kg_co2e_yr": net,
                    },
                )
        result = GateResult(
            pr_number=self.pr,
            base_sha=base_sha,
            head_sha=head_sha,
            status=status,  # type: ignore[arg-type]
            net_kg_co2e_yr=net,
            net_kg_co2e_yr_low=low,
            net_kg_co2e_yr_high=high,
            changes=changes,
            projections=projections,
            suggestions=suggestions,
            accepted_by=accepted_by,
            accepted_reason=accepted_reason,
            ledger_run_id=c.ledger.run_id,
            projection_event_id=getattr(self, "_projection_event", None),
        )
        measurement = tracker.stop()
        runtime_s = time.monotonic() - t0
        comment = None
        if not no_comment:
            comment = reporter.gate_comment(
                result,
                gate_cfg,
                c.factors,
                int(c.policy.thresholds["lookback_days"]),
                runtime_s,
                measurement.energy_kwh * 1000 if measurement else None,
                measurement.label if measurement else None,
                reason,
                c.notes,
            )
        prediction = GatePrediction(
            repo=self.repo or "local",
            pr_number=self.pr,
            head_sha=head_sha,
            base_sha=base_sha,
            created_at=started,
            factor_version=c.factors.version,
            projections=projections,
        )
        (run_dir / "prediction.json").write_text(
            prediction.model_dump_json(indent=1), encoding="utf-8"
        )
        (run_dir / "gate_result.json").write_text(
            result.model_dump_json(indent=1), encoding="utf-8"
        )
        if comment:
            (run_dir / "comment.md").write_text(comment, encoding="utf-8", newline="\n")
        url = None
        if comment and self.github is not None and self.pr:
            try:
                url = self.github.upsert_comment(self.pr, comment)
                c.ledger.append(
                    state=status.upper(),
                    kind="tool_call",
                    agent="reporter",
                    tool="github.upsert_comment",
                    detail={"pr": self.pr},
                )
            except GitHubError as exc:
                c.ledger.append(
                    state=status.upper(),
                    kind="fallback",
                    agent="reporter",
                    tool="github.upsert_comment",
                    detail={"reason": str(exc)[:300], "comment_in_job_log": True},
                )
        c.ledger.append(
            state=status.upper(),
            kind="transition",
            detail={"status": status, "net_kg_co2e_yr": net, "low": low, "high": high},
        )
        c.ledger.close()
        exit_code = 1 if status == "ack_required" and self.github is not None else 0
        return GateRun(result, comment, run_dir, exit_code, url, c.notes)


def _diff(path: str, old: str, new: str) -> str:
    from emissiongate.agents.validator import unified_diff

    return unified_diff(path, old, new)
