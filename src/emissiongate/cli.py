"""EmissionGate command line. The only module that prints; everything else logs."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from emissiongate.config import load_settings

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


@app.command()
def run(
    mode: str = typer.Option("offline", help="offline | local | live"),
    seed: int = typer.Option(42),
    approve: bool = typer.Option(False, "--approve", help="Gate 1: approve scope and budget."),
) -> None:
    """Sweep the estate: quantify, rank, render, validate, draft PRs."""


@app.command()
def gate() -> None:
    """Check a pull request's carbon delta (base vs head)."""


@app.command()
def score(latest: bool = typer.Option(False, "--latest")) -> None:
    """Score a run against the ground truth."""


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
