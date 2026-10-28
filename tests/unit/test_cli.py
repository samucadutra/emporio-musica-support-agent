"""CLI commands, with fake embeddings (no model download)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from emporio_musica_support_agent import cli
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.data.loader import policy_path
from emporio_musica_support_agent.rag.index import PolicyIndex
from fakes import FakeEmbeddings


@pytest.fixture
def fake_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, data_dir: Path) -> PolicyIndex:
    index = PolicyIndex(tmp_path / "chroma", FakeEmbeddings(), policy_path(data_dir), "fake")

    def make(settings: Settings) -> PolicyIndex:
        return index

    monkeypatch.setattr(cli, "make_policy_index", make)
    return index


def test_help_lists_ingest(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "ingest" in result.output


def test_ingest_twice_is_up_to_date(cli_runner: CliRunner, fake_index: PolicyIndex) -> None:
    first = cli_runner.invoke(cli.app, ["ingest"])
    second = cli_runner.invoke(cli.app, ["ingest"])

    assert first.exit_code == 0, first.output
    assert "Indexed 26 policy chunks" in first.output
    assert "pdf_sha256" in first.output
    assert second.exit_code == 0
    assert "up to date (26 chunks)" in second.output


def test_ingest_force_rebuilds(cli_runner: CliRunner, fake_index: PolicyIndex) -> None:
    cli_runner.invoke(cli.app, ["ingest"])

    result = cli_runner.invoke(cli.app, ["ingest", "--force"])

    assert result.exit_code == 0
    assert "Indexed 26 policy chunks" in result.output


def test_ingest_missing_pdf_fails(
    cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    result = cli_runner.invoke(cli.app, ["ingest"])

    assert result.exit_code == 1
    assert "políticas_da_loja.pdf" in result.output
