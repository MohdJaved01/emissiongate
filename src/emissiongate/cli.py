"""EmissionGate command line. The only module that prints; everything else logs."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from emissiongate.config import load_settings
from emissiongate.report.render import published_delta

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(
            encoding="utf-8", errors="replace"
        )  # Windows consoles default to cp1252
console = Console()
app = typer.Typer(
    help="EmissionGate: carbon at merge time. All data is synthetic.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def estate(
    seed: int = typer.Option(42, help="Seed for the synthetic estate."),
    out: Path | None = typer.Option(None, help="Data directory (default: data/)."),
    terraform_out: Path | None = typer.Option(None, help="Terraform directory (EG_ESTATE_DIR)."),
    telemetry_only: bool = typer.Option(
        False, "--telemetry-only", help="CUR, metrics and prices only; no Terraform (gate CI)."
    ),
) -> None:
    """Generate the synthetic estate, telemetry and ground truth (all synthetic)."""
    from emissiongate.core.factors import FACTORS_FILE, Factors
    from emissiongate.estate.generator import SPECS, generate

    settings = load_settings()
    data_dir = out or settings.data_dir
    tf_dir = None if telemetry_only else (terraform_out or settings.estate_dir)
    factors = Factors.load(settings.factors_dir / FACTORS_FILE)
    manifest = generate(seed, data_dir, tf_dir, settings.versions_tf, factors, telemetry_only)
    console.print(
        f"[bold]Synthetic estate[/bold] seed={seed}: {len(SPECS)} resource groups, "
        f"{len(manifest['files'])} files -> {data_dir}"
        + (f" and {tf_dir}" if tf_dir else " (telemetry only)")
    )
    gt = [s.resource_id for s in SPECS]
    console.print(f"Resources: {', '.join(gt)}")
    console.print("Traps (must be refused): dr-standby, monthend-close, compliance-logs")


def _approver() -> str:
    return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown-human"


def _f(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}"


def _progress(kind: str, data: dict) -> None:
    if kind == "scoped":
        console.print(
            f"[green]Gate 1 approved[/green] by {data['approved_by']} · run {data['run_id']}"
        )
    elif kind == "transition":
        console.print(f"[dim]state {data['from']} -> {data['to']}[/dim]")
    elif kind == "collected" and data["skipped"]:
        for rid, why in data["skipped"]:
            console.print(f"[yellow]skipped[/yellow] {rid}: {why}")
    elif kind == "quantified":
        facts = {f.resource.resource_id: f.resource for f in data["facts"]}
        t = Table(title="Quantifier: kgCO2e per resource (deterministic core, annual tier)")
        for col in ("resource", "shape", "region", "kWh/yr", "kgCO2e/yr", "provenance", "ledger"):
            t.add_column(col, justify="right" if col in ("kWh/yr", "kgCO2e/yr") else "left")
        for rid, rec in sorted(data["records"].items(), key=lambda kv: -kv[1].kg_co2e_yr):
            r = facts[rid]
            shape = (
                f"{r.count} x {r.instance_type}"
                if r.instance_type
                else f"{r.storage_tb:.1f} TB {r.storage_class}"
            )
            prov = ", ".join(sorted({f"{p.source}/{p.tier}" for p in rec.provenance}))
            t.add_row(
                rid,
                shape,
                r.region,
                _f(rec.kwh_yr),
                _f(rec.kg_co2e_yr),
                prov,
                f"#{rec.ledger_event_id}",
            )
        console.print(t)
    elif kind == "ranked":
        s = data["strategy"]
        t = Table(title="Ranked by carbon (cost shown, never used to rank)")
        for col in ("carbon", "cost", "option", "kgCO2e/yr saved", "USD/yr saved (synthetic)"):
            t.add_column(col, justify="right" if col != "option" else "left")
        for cid, (rc, rcost) in sorted(s.ranks_all.items(), key=lambda kv: kv[1][0]):
            v = s.valuations[cid]
            saved = -published_delta(v.kg_co2e_before_yr, v.kg_co2e_after_yr)
            t.add_row(str(rc), str(rcost), cid, _f(saved), f"{v.usd_synthetic_saved_yr:,.0f}")
        console.print(t)
        for a in s.advisories:
            colour = "red" if a.kind == "guardrail" else "yellow"
            blocked = f" ({', '.join(a.blocked_by)})" if a.blocked_by else ""
            console.print(
                f"[{colour}]{a.kind:>21}[/{colour}] {a.resource_id}: {escape(a.reason + blocked)}"
            )
        for rid, reasons in sorted(s.no_action.items()):
            console.print(f"[yellow]{'no action':>21}[/yellow] {rid}: {'; '.join(reasons)}")
    elif kind == "decided":
        d = data["decision"]
        console.print(
            f"[cyan]decide[/cyan] {d.candidate_id} by {data['by']}: {d.template} "
            + escape(str(d.params))
        )
    elif kind == "validated":
        v, row = data["validation"], data["row"]
        for a in v.attempts:
            mark = "[green]plan ok[/green]" if a.ok else "[red]plan failed[/red]"
            console.print(f"   attempt {a.attempt}: {mark} ({a.command})")
            if not a.ok:
                console.print(f"[dim]{a.stderr_tail.strip()[-300:]}[/dim]")
        console.print(f"   -> {row['status']}: {row['title']}")
    elif kind in ("failed", "budget"):
        console.print(f"[red]{kind}[/red]: {data}")


@app.command()
def run(
    mode: str = typer.Option("offline", help="offline | local | live"),
    seed: int = typer.Option(42),
    approve: bool = typer.Option(False, "--approve", help="Gate 1: approve scope and budget."),
    inject: list[str] = typer.Option([], help="Failure injection: bad-param (repeatable)."),
) -> None:
    """Sweep the estate: quantify, rank, render, validate, draft PRs."""
    from emissiongate.orchestrator.machine import Machine

    settings = load_settings()
    if mode == "live":
        console.print("[red]Live mode (real PRs) is designed, not built in this submission.[/red]")
        raise typer.Exit(2)
    if not (settings.data_dir / "cur" / "usage.parquet").exists():
        console.print("No estate found: run `emissiongate estate --seed 42` first.")
        raise typer.Exit(1)
    ceilings = settings.policy()["ceilings"]
    console.print(
        f"[bold]Scope[/bold]: estate {settings.estate_dir} (synthetic, seed {seed}), mode {mode}; "
        f"budget: {ceilings['max_prs_per_run']} PRs, "
        f"{ceilings['max_llm_calls_per_run']} LLM calls, "
        f"{ceilings['max_tokens_per_run']} tokens, {ceilings['max_repair_attempts']} repairs, "
        f"{ceilings['max_wall_seconds']} s."
    )
    if not approve and not typer.confirm("Gate 1: approve this scope and budget?", default=False):
        console.print("Not approved. Nothing was started.")
        raise typer.Exit(1)
    llm, note = None, None
    if mode == "local":
        from emissiongate.llm.factory import make_client

        llm, note = make_client(settings)
        console.print(note)
    result = Machine(
        settings,
        mode,
        seed,
        _approver(),
        inject=tuple(inject),
        llm=llm,
        llm_note=note if mode == "local" else None,
        progress=_progress,
    ).run()
    m = result.manifest
    console.print(
        f"[bold]{m.final_state}[/bold]: {m.counts['drafted']} PR drafts, "
        f"{m.counts['escalated']} escalated, coverage {m.coverage:.0%}, "
        f"LLM calls {m.llm['calls']} ({m.llm['prompt_tokens'] + m.llm['completion_tokens']} tokens)"
    )
    if m.sci:
        console.print(
            f"Agent footprint: {m.sci.energy_kwh:.6f} kWh ({m.sci.energy_label}), "
            f"{m.sci.kg_co2e_per_run * 1000:.3f} gCO2e this run; "
            f"payback (proposed) {m.sci.payback_ratio_proposed or 0:,.0f}x"
        )
    console.print(f"Report: {result.run_dir / 'report.html'}")
    if m.final_state == "FAILED":
        raise typer.Exit(1)


def _latest_run(runs_dir: Path, offset: int = 0) -> Path:
    runs = sorted(
        (p for p in runs_dir.glob("*-s*") if (p / "manifest.json").exists()),
        key=lambda p: p.name,
    )
    if len(runs) <= offset:
        console.print(f"No finished runs in {runs_dir}.")
        raise typer.Exit(1)
    return runs[-1 - offset]


def score_run(run_dir: Path, data_dir: Path) -> dict:
    from emissiongate.contracts import GroundTruthEntry
    from emissiongate.core.scoring import score as score_fn

    truth_doc = json.loads((data_dir / "ground_truth.json").read_text(encoding="utf-8"))
    truth = [GroundTruthEntry(**e) for e in truth_doc["entries"]]
    prs = json.loads((run_dir / "prs" / "index.json").read_text(encoding="utf-8"))
    strat = json.loads((run_dir / "strategy.json").read_text(encoding="utf-8"))
    result = score_fn(truth, prs, strat["carbon_order"], strat["cost_order"])
    doc = result.model_dump()
    (run_dir / "score.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc


@app.command()
def score(
    latest: bool = typer.Option(True, "--latest", help="Score the most recent run."),
    run_id: str | None = typer.Option(None, help="Score this run instead."),
    compare_latest: int = typer.Option(0, help="Score the N most recent runs side by side."),
) -> None:
    """Score a run against the seeded ground truth (precision, recall, trap violations)."""
    settings = load_settings()
    runs = (
        [settings.runs_dir / run_id]
        if run_id
        else [_latest_run(settings.runs_dir, i) for i in range(max(1, compare_latest))]
    )
    t = Table(title="Score vs ground truth (seed 42, synthetic)")
    for col in ("run", "precision", "recall", "TP/FP/FN", "trap violations"):
        t.add_column(col)
    for run_dir in runs:
        s = score_run(run_dir, settings.data_dir)
        p = "n/a" if s["precision"] is None else f"{s['precision']:.2f}"
        r = "n/a" if s["recall"] is None else f"{s['recall']:.2f}"
        tv = ", ".join(s["trap_violations"]) or "0"
        t.add_row(
            run_dir.name,
            p,
            r,
            f"{s['true_positives']}/{s['false_positives']}/{s['false_negatives']}",
            tv,
        )
    console.print(t)
    s = score_run(runs[0], settings.data_dir)
    console.print(f"carbon order: {' > '.join(s['carbon_rank_order'])}")
    console.print(f"cost order:   {' > '.join(s['cost_rank_order'])}")
    if s["trap_violations"]:
        raise typer.Exit(1)


@app.command("sync-feedback")
def sync_feedback() -> None:
    """Read closed PR labels and gate predictions (live mode; designed, not built)."""


@app.command("grid-snapshot")
def grid_snapshot() -> None:
    """Fetch a UK grid-intensity snapshot (network; human-run)."""


@app.command()
def report() -> None:
    """Re-render the report of a finished run."""


@app.command()
def bakeoff() -> None:
    """Model bake-off (designed, not built)."""
