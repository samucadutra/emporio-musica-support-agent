"""Smoke tests: the package imports and the CLI starts."""

import typer
from typer.testing import CliRunner

import emporio_musica_support_agent
from emporio_musica_support_agent.cli import app


def test_package_imports() -> None:
    assert emporio_musica_support_agent.__name__ == "emporio_musica_support_agent"
    assert isinstance(app, typer.Typer)


def test_cli_help(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Usage" in result.output
