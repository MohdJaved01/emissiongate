"""Run-level and candidate-level state machines (ARCHITECTURE §3–4). Plain Python, no framework.

SCOPED -> COLLECTING -> QUANTIFIED -> RANKED -> DELIVERING -> DONE, with BUDGET_STOPPED and FAILED.
`checkpoint.json` is written before every transition; every transition is a ledger event.
"""

from __future__ import annotations

import csv
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from emissiongate.agents import collector, decider, quantifier, strategist, validator
from emissiongate.agents.context import RunContext
from emissiongate.config import Settings
from emissiongate.contracts import Candidate, PullRequestDraft, RunManifest
from emissiongate.core import grid
from emissiongate.core.factors import FACTORS_FILE, Factors
from emissiongate.core.interventions import Prices, Valuation
from emissiongate.core.ledger import Ledger, LedgerWriteError
from emissiongate.core.policy import Policy
from emissiongate.core.sci import sci
from emissiongate.orchestrator import checkpoint
from emissiongate.orchestrator.budget import Budget, BudgetExceeded
from emissiongate.orchestrator.measure import Measurement, Tracker
from emissiongate.report.render import change_summary, published_delta, render_html, render_markdown
from emissiongate.tools import tf

log = logging.getLogger(__name__)
WINDOW_END = datetime(2026, 10, 1, tzinfo=UTC)  # telemetry window end of the synthetic estate
MINUS = "−"

Progress = Callable[[str, dict], None]


@dataclass
class SweepResult:
    manifest: RunManifest
    run_dir: Path
    drafts: list[PullRequestDraft] = field(default_factory=list)
    strategy: strategist.Strategy | None = None
    records: dict = field(default_factory=dict)


def new_run_id(mode: str, seed: int, now: datetime) -> str:
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{mode}-s{seed}"


def latest_snapshot(snapshot_dir: Path) -> grid.GridSnapshot | None:
    files = sorted(snapshot_dir.glob("uk_london_*.json"))
    if not files:
        return None
    return grid.parse_snapshot(json.loads(files[-1].read_text(encoding="utf-8")))


def _title(template: str, rid: str, params: dict[str, str], delta: float, old: str | None) -> str:
    d = f"{delta:+,.1f}".replace("-", MINUS)
    titles = {
        "schedule": f"Schedule {rid} to its weekly activity window ({d} kgCO2e/yr)",
        "graviton": f"Move {rid} to Graviton {params.get('target_instance_type')} ({d} kgCO2e/yr)",
        "rightsize": (
            f"Rightsize {rid}: {old} to {params.get('target_instance_type')} ({d} kgCO2e/yr)"
        ),
        "storage_tier": f"Tier {rid} to {params.get('storage_class')} ({d} kgCO2e/yr)",
        "time_shift": f"Shift {rid} to a lower-carbon window ({d} kgCO2e/yr)",
    }
    return titles[template]


def _reconciliation(data_dir: Path, records: dict, facts: dict) -> list[dict]:
    path = data_dir / "ccft" / "monthly.csv"
    if not path.exists():
        return []
    monthly: dict[str, list[float]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            monthly.setdefault(row["region"], []).append(float(row["kg_co2e"]))
    bottom: dict[str, float] = {}
    for rid, rec in records.items():
        region = facts[rid].resource.region
        bottom[region] = bottom.get(region, 0.0) + rec.kg_co2e_yr / 12
    rows = []
    for region in sorted(bottom):
        if region not in monthly or not bottom[region]:
            continue
        ccft = sum(monthly[region]) / len(monthly[region])
        rows.append(
            {
                "region": region,
                "bottom_up": bottom[region],
                "ccft": ccft,
                "variance": (ccft - bottom[region]) / bottom[region] * 100,
            }
        )
    return rows


def _escalation_body(title: str, v: validator.Validation) -> str:
    last = v.attempts[-1] if v.attempts else None
    command = last.command if last else "n/a"
    tail = last.stderr_tail if last else ""
    return (
        f"## ESCALATED: {title}\n\n"
        f"EmissionGate could not produce a change that passes `tofu plan` ({v.error}). "
        "A human should look at this candidate. No PR is proposed.\n\n"
        f"Last command: `{command}`\n\n```\n{tail}\n```\n"
    )


class Machine:
    def __init__(
        self,
        settings: Settings,
        mode: str,
        seed: int,
        approved_by: str,
        inject: tuple[str, ...] = (),
        llm: object | None = None,
        llm_note: str | None = None,
        progress: Progress | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.settings = settings
        self.mode = mode
        self.seed = seed
        self.approved_by = approved_by
        self.inject = inject
        self.llm = llm
        self.llm_note = llm_note
        self.progress = progress or (lambda kind, data: None)
        self.clock = clock

    def _transition(self, ctx: RunContext, to: str, data: dict | None = None) -> None:
        checkpoint.write(ctx.run_dir, to, {"run_id": ctx.run_id, **(data or {})})
        ctx.ledger.append(state=to, kind="transition", detail={"from": ctx.state, "to": to})
        self.progress("transition", {"from": ctx.state, "to": to})
        ctx.state = to

    def run(self) -> SweepResult:
        s = self.settings
        started = self.clock()
        run_id = new_run_id(self.mode, self.seed, started)
        run_dir = s.runs_dir / run_id
        (run_dir / "prs").mkdir(parents=True, exist_ok=True)
        tracker = Tracker(s.country_iso)
        tracker.start()
        wall0 = time.monotonic()
        ledger = Ledger(run_dir / "ledger.sqlite", run_id, self.clock)
        policy = Policy.from_docs(s.policy(), s.suppressions())
        tofu_cfg = tf.TofuConfig(
            bin=s.tofu_bin, plugin_dir=s.tofu_plugin_dir, data_dir=s.cwd / ".eg-cache" / "tofu-data"
        )
        ctx = RunContext(
            run_id=run_id,
            run_dir=run_dir,
            mode=self.mode,
            data_dir=s.data_dir,
            estate_dir=s.estate_dir,
            factors=Factors.load(s.factors_dir / FACTORS_FILE),
            policy=policy,
            ledger=ledger,
            tofu=tofu_cfg,
            reference=WINDOW_END,
            today=date.fromisoformat(started.date().isoformat()),
            llm=self.llm,
            budget=Budget(policy.ceilings),
            inject=self.inject,
        )
        ledger.append(
            state="SCOPED",
            kind="human_gate",
            detail={
                "gate": "Gate 1: scope and budget",
                "approved_by": self.approved_by,
                "mode": self.mode,
                "seed": self.seed,
                "inject": ",".join(self.inject),
            },
        )
        self.progress("scoped", {"run_id": run_id, "approved_by": self.approved_by})
        final_state = "DONE"
        drafts: list[PullRequestDraft] = []
        validations: list[validator.Validation] = []
        draft_rows: list[dict] = []
        records: dict = {}
        strategy = strategist.Strategy()
        facts: list = []
        skipped: list = []
        try:
            self._transition(ctx, "COLLECTING")
            prices_path = s.data_dir / "prices_synthetic.json"
            ctx.prices = Prices.from_doc(json.loads(prices_path.read_text(encoding="utf-8")))
            ctx.grid_snapshot = latest_snapshot(s.grid_snapshot_dir)
            facts, skipped = collector.collect(ctx)
            self.progress("collected", {"facts": facts, "skipped": skipped})
            ctx.budget.check()

            self._transition(ctx, "QUANTIFIED")
            records, not_quantified = quantifier.quantify(ctx, facts)
            skipped += not_quantified
            self.progress("quantified", {"records": records, "facts": facts})

            self._transition(ctx, "RANKED")
            strategy = strategist.strategise(ctx, facts, records)
            self.progress("ranked", {"strategy": strategy})

            self._transition(
                ctx, "DELIVERING", {"candidates": [c.candidate_id for c in strategy.candidates]}
            )
            max_attempts = int(policy.ceilings["max_repair_attempts"])
            with tf.Workspace(tofu_cfg, s.estate_dir) as ws:
                for cand in strategy.candidates:
                    ctx.budget.check()
                    if not ctx.budget.pr_slot():
                        self.progress("budget", {"reason": "max_prs_per_run"})
                        break
                    decision, decided_by = decider.decide(ctx, strategy, cand)
                    self.progress(
                        "decided", {"candidate": cand, "decision": decision, "by": decided_by}
                    )
                    v = validator.validate(
                        ctx,
                        ws,
                        strategy.facts[cand.resource_id],
                        cand,
                        decision,
                        strategy.verdicts[cand.resource_id].forbid,
                        decider.repair_fn(ctx),
                        max_attempts,
                    )
                    validations.append(v)
                    valuation = strategist.revalue(ctx, strategy, v.decision)
                    draft, row = self._draft(ctx, strategy, cand, v, valuation, records, decided_by)
                    drafts.append(draft)
                    draft_rows.append(row)
                    if draft.status == "drafted":
                        ctx.budget.charge_pr()
                    self.progress("validated", {"candidate": cand, "validation": v, "row": row})
            self._transition(ctx, "DONE")
        except BudgetExceeded as exc:
            final_state = "BUDGET_STOPPED"
            ledger.append(state="BUDGET_STOPPED", kind="budget", detail={"ceiling": exc.ceiling})
            checkpoint.write(run_dir, "BUDGET_STOPPED", {"run_id": run_id})
            self.progress("budget", {"reason": exc.ceiling})
        except (FileNotFoundError, tf.TofuError) as exc:
            final_state = "FAILED"
            ledger.append(
                state="FAILED",
                kind="tool_call" if isinstance(exc, tf.TofuError) else "error",
                agent="validator" if isinstance(exc, tf.TofuError) else "orchestrator",
                tool="tofu.init" if isinstance(exc, tf.TofuError) else None,
                detail={"error": str(exc)[:500]},
            )
            checkpoint.write(run_dir, "FAILED", {"run_id": run_id, "error": str(exc)})
            self.progress("failed", {"error": str(exc)})
        except LedgerWriteError:
            checkpoint.write(run_dir, "FAILED", {"run_id": run_id, "error": "ledger write failed"})
            raise

        measurement = tracker.stop()
        wall = time.monotonic() - wall0
        proposed_kg = sum(r["kg_saved"] for r in draft_rows)
        manifest = self._manifest(
            ctx,
            started,
            final_state,
            facts,
            skipped,
            records,
            drafts,
            validations,
            measurement,
            wall,
            proposed_kg,
        )
        (run_dir / "manifest.json").write_text(manifest.model_dump_json(indent=1), encoding="utf-8")
        index = [
            d.model_dump()
            | {
                "resource_id": d.candidate_id.split(":")[0],
                "intervention": d.candidate_id.split(":")[1],
            }
            for d in drafts
        ]
        (run_dir / "prs" / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
        (run_dir / "strategy.json").write_text(
            json.dumps(
                {
                    "carbon_order": [
                        c.resource_id
                        for c in sorted(strategy.candidates, key=lambda c: c.rank_carbon)
                    ],
                    "cost_order": [
                        c.resource_id
                        for c in sorted(strategy.candidates, key=lambda c: c.rank_cost)
                    ],
                    "advisories": [a.model_dump() for a in strategy.advisories],
                    "no_action": strategy.no_action,
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        self._report(ctx, manifest, facts, records, strategy, draft_rows)
        ledger.close()
        return SweepResult(manifest, run_dir, drafts, strategy, records)

    # ---- helpers ---------------------------------------------------------------------------

    def _draft(
        self,
        ctx: RunContext,
        strategy: strategist.Strategy,
        cand: Candidate,
        v: validator.Validation,
        valuation: Valuation,
        records: dict,
        decided_by: str,
    ) -> tuple[PullRequestDraft, dict]:
        rid = cand.resource_id
        f = strategy.facts[rid]
        old_type = f.resource.instance_type
        delta = published_delta(valuation.kg_co2e_before_yr, valuation.kg_co2e_after_yr)
        title = _title(cand.intervention, rid, v.decision.params, delta, old_type)
        source = "template"
        valued_event = strategist.ledger_valuation(ctx, valuation, "validator")
        if v.ok:
            narrative, risks, source = decider.narrate(ctx, cand, valuation)
            body = render_markdown(
                "pr_body.md.j2",
                title=title,
                mode=ctx.mode,
                run_id=ctx.run_id,
                v=valuation,
                change=change_summary(cand.intervention, v.decision.params, old_type),
                narrative=narrative,
                narrative_source=source,
                risks=risks,
                util=f.util,
                resource=f.resource,
                attempts=len(v.attempts),
                record=records[rid],
                event_ids=v.event_ids,
                valued_event=valued_event,
                diff=v.diff,
            )
        else:
            body = _escalation_body(title, v)
        draft = validator.draft(cand, v, title, body)
        name = f"{rid}.md" if v.ok else f"{rid}.escalated.md"
        (ctx.run_dir / "prs" / name).write_text(body, encoding="utf-8", newline="\n")
        row = {
            "file": name,
            "resource_id": rid,
            "title": title,
            "template": cand.intervention,
            "delta": delta,
            "attempts": len(v.attempts),
            "repaired": len(v.attempts) > 1 and v.ok,
            "decided_by": decided_by,
            "narrative_source": source,
            "status": draft.status,
            "kg_saved": valuation.kg_co2e_saved_yr if v.ok else 0.0,
        }
        return draft, row

    def _manifest(
        self,
        ctx: RunContext,
        started: datetime,
        final_state: str,
        facts: list,
        skipped: list,
        records: dict,
        drafts: list[PullRequestDraft],
        validations: list,
        measurement: Measurement | None,
        wall_s: float,
        proposed_kg: float,
    ) -> RunManifest:
        summary = ctx.ledger.summary()
        in_scope = len({f.resource.resource_id for f in facts} | {r for r, _ in skipped})
        drafted = sum(1 for d in drafts if d.status == "drafted")
        sci_result = None
        if measurement is not None:
            sci_result = sci(
                energy_kwh=measurement.energy_kwh,
                energy_label="measured" if measurement.label == "measured" else "estimated",
                tracking_method=measurement.tracking_method,
                grid_g_per_kwh=measurement.g_per_kwh,
                grid_source=measurement.grid_source,
                run_seconds=wall_s,
                device_embodied_kg=self.settings.device_embodied_kg_co2e,
                device_lifespan_years=self.settings.device_lifespan_years,
                proposed_kg_yr=proposed_kg,
                merged_kg_yr=None,
                accepted_recommendations=0,
            )
        models: dict[str, str] = {}
        if self.llm is not None:
            st = self.settings
            models = {
                "small": f"{st.model_small}@{st.think_small}",
                "large": f"{st.model_large}@{st.think_large}",
            }
        return RunManifest(
            run_id=ctx.run_id,
            mode=self.mode,  # type: ignore[arg-type]
            seed=self.seed,
            started_at=started,
            finished_at=self.clock(),
            final_state=final_state,  # type: ignore[arg-type]
            approved_by=self.approved_by,
            coverage=len(records) / in_scope if in_scope else 0.0,
            counts={
                "in_scope": in_scope,
                "quantified": len(records),
                "candidates": len(drafts),
                "drafted": drafted,
                "opened": 0,
                "escalated": sum(1 for d in drafts if d.status == "escalated"),
                "skipped": len(skipped),
            },
            llm={
                "calls": summary["llm_calls"],
                "prompt_tokens": summary["prompt_tokens"],
                "completion_tokens": summary["completion_tokens"],
                "fallbacks": summary["fallbacks"],
            },
            repair_attempts=sum(max(0, len(v.attempts) - 1) for v in validations),
            first_attempt_plan_success=(
                sum(1 for v in validations if v.first_attempt_ok) / len(validations)
                if validations
                else None
            ),
            factors_version=ctx.factors.version,
            models=models,
            tofu_version=self._tofu_version(ctx),
            sci=sci_result,
        )

    def _tofu_version(self, ctx: RunContext) -> str | None:
        version = tf.version(ctx.tofu)
        ctx.ledger.append(
            state=ctx.state,
            kind="tool_call",
            agent="orchestrator",
            tool="tofu.version",
            detail={"version": version},
        )
        return version

    def _report(
        self,
        ctx: RunContext,
        manifest: RunManifest,
        facts: list,
        records: dict,
        strategy: strategist.Strategy,
        draft_rows: list[dict],
    ) -> Path:
        facts_by_id = {f.resource.resource_id: f for f in facts}
        rows = sorted(records.items(), key=lambda kv: -kv[1].kg_co2e_yr)
        delivered = {r["resource_id"]: r for r in draft_rows if r["status"] == "drafted"}
        selected = {c.candidate_id for c in strategy.candidates}
        below = {
            (a.resource_id, a.reason.split(":")[0])
            for a in strategy.advisories
            if a.kind == "below_threshold"
        }
        ranking = []
        for cid, (rc, rcost) in sorted(strategy.ranks_all.items(), key=lambda kv: kv[1][0]):
            rid, intervention = cid.split(":")
            if rid in delivered and delivered[rid]["template"] == intervention:
                outcome = "PR drafted"
            elif (rid, intervention) in below:
                outcome = "advisory: below carbon threshold"
            elif cid in selected:
                outcome = "selected, not delivered"
            else:
                outcome = "alternative (smaller carbon saving)"
            v = strategy.valuations[cid]
            ranking.append(
                {
                    "tiers": ", ".join(sorted({p.tier for p in v.provenance} - {"vendored"})),
                    "event": strategy.valuation_events.get(cid),
                    "cid": cid,
                    "rank_carbon": rc,
                    "rank_cost": rcost,
                    "v": strategy.valuations[cid],
                    "outcome": outcome,
                }
            )
        refused = len({a.resource_id for a in strategy.advisories} | set(strategy.no_action))
        html = render_html(
            "report.html.j2",
            m=manifest,
            records=[(facts_by_id[rid].resource, rec) for rid, rec in rows],
            totals={
                "estate_kg": sum(r.kg_co2e_yr for r in records.values()),
                "proposed_kg": sum(r["kg_saved"] for r in draft_rows),
            },
            drafted=sum(1 for r in draft_rows if r["status"] == "drafted"),
            refused=refused,
            ranking=ranking,
            advisories=strategy.advisories,
            no_action=strategy.no_action,
            drafts=draft_rows,
            ledger=ctx.ledger.summary(),
            reconciliation=_reconciliation(ctx.data_dir, records, facts_by_id),
            llm_note=self.llm_note,
            grid_attribution=ctx.grid_snapshot is not None,
        )
        path = ctx.run_dir / "report.html"
        path.write_text(html, encoding="utf-8", newline="\n")
        return path


__all__ = ["Machine", "SweepResult", "latest_snapshot", "new_run_id"]
