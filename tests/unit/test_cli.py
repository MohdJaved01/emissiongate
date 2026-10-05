from typer.testing import CliRunner

from emissiongate.cli import app


def test_help_lists_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ["estate", "run", "gate", "score", "sync-feedback", "grid-snapshot", "report"]:
        assert command in result.output
