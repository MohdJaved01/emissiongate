"""EmissionGate command line. The only module that prints; everything else logs."""

from __future__ import annotations

import typer

app = typer.Typer(
    help="EmissionGate: carbon at merge time. All data is synthetic.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def estate(seed: int = typer.Option(42, help="Seed for the synthetic estate.")) -> None:
    """Generate the synthetic estate, telemetry and ground truth."""


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
