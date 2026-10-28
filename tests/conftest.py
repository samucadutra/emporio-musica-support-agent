"""Shared pytest fixtures."""

import logging
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.data.repository import Repository
from emporio_musica_support_agent.logging_setup import LOGGER_NAME

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


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def captured_events() -> Iterator[Callable[[str], list[dict[str, object]]]]:
    """Capture structured log events from the package logger, wherever it propagates.

    Returns a function: event name -> the `fields` of each matching record.
    """
    logger = logging.getLogger(LOGGER_NAME)
    handler = _ListHandler()
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    def events(name: str) -> list[dict[str, object]]:
        matching = (r for r in handler.records if getattr(r, "event", None) == name)
        return [dict(getattr(r, "fields", {})) for r in matching]

    yield events
    logger.removeHandler(handler)
    logger.setLevel(previous_level)


@pytest.fixture
def tmp_settings(tmp_path: Path, data_dir: Path) -> Settings:
    """Settings with every generated file under tmp_path and the real data."""
    var = tmp_path / "var"
    return Settings(
        _env_file=None,
        data_dir=data_dir,
        var_dir=var,
        chroma_dir=var / "chroma",
        models_cache_dir=var / "models",
        sqlite_path=var / "agent.db",
        handoff_log_path=var / "handoffs.jsonl",
        log_file=var / "logs" / "agent.jsonl",
        store_today=None,
    )
