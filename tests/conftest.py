"""Shared pytest fixtures."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).parents[1]


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return REPO_ROOT / "data"
