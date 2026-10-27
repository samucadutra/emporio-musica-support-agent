"""Shared pytest fixtures."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from emporio_musica_support_agent.data.repository import Repository

REPO_ROOT = Path(__file__).parents[1]


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return REPO_ROOT / "data"


@pytest.fixture(scope="session")
def repo(data_dir: Path) -> Repository:
    return Repository.load(data_dir)
