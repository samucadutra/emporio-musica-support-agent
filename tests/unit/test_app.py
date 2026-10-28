"""Dependency wiring (design §2)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from emporio_musica_support_agent.app import build_deps
from emporio_musica_support_agent.clock import FixedClock, SystemClock
from emporio_musica_support_agent.config import Settings
from fakes import FakeEmbeddings


def test_build_deps_loads_data_and_creates_dirs(tmp_settings: Settings) -> None:
    deps = build_deps(tmp_settings, embeddings=FakeEmbeddings())

    assert len(deps.repo.data.products) == 65
    assert tmp_settings.chroma_dir.is_dir()
    assert tmp_settings.log_file.parent.is_dir()
    assert deps.handoff_log.path == tmp_settings.handoff_log_path
    assert deps.policy_index.chroma_dir == tmp_settings.chroma_dir
    assert isinstance(deps.clock, SystemClock)


def test_build_deps_keeps_given_clock(tmp_settings: Settings) -> None:
    clock = FixedClock(datetime(2026, 2, 20, 10, tzinfo=ZoneInfo("America/Campo_Grande")))

    assert build_deps(tmp_settings, clock=clock, embeddings=FakeEmbeddings()).clock is clock
