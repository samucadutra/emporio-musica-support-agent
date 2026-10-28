"""Settings defaults, `.env` parsing and provider env export."""

import os
import shutil
from datetime import date
from pathlib import Path

import pytest
from pydantic import SecretStr

from emporio_musica_support_agent.config import PROVIDER_ENV_VARS, Settings

ENV_EXAMPLE = Path(__file__).parents[2] / ".env.example"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep the shell environment and any real `.env` out of these tests."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    for name in list(os.environ):
        if name.startswith("LANGSMITH_"):
            monkeypatch.delenv(name)
    # Registered with monkeypatch so values set by export_provider_env are undone.
    for name in (*PROVIDER_ENV_VARS, "LANGSMITH_PROJECT", "LANGSMITH_TRACING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def write_env(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.llm_model == "google_genai:gemini-3.8-flash"
    assert settings.llm_temperature == 0.2
    assert settings.llm_timeout_s == 60
    assert settings.llm_max_retries == 4
    assert settings.google_api_key is None
    assert settings.openai_api_key is None
    assert settings.anthropic_api_key is None
    assert settings.ollama_base_url is None
    assert settings.embedding_model == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert settings.data_dir == Path("data")
    assert settings.var_dir == Path("var")
    assert settings.chroma_dir == Path("var/chroma")
    assert settings.models_cache_dir == Path("var/models")
    assert settings.sqlite_path == Path("var/agent.db")
    assert settings.handoff_log_path == Path("var/handoffs.jsonl")
    assert settings.log_level == "INFO"
    assert settings.log_file == Path("var/logs/agent.jsonl")
    assert settings.store_timezone == "America/Campo_Grande"
    assert settings.store_today is None
    assert settings.max_tool_rounds == 6
    assert settings.retrieval_k == 4
    assert settings.eval_delay_s == 4


def test_env_file_parsing(tmp_path: Path) -> None:
    env_file = write_env(
        tmp_path,
        "LLM_MODEL=openai:gpt-4.1-mini\nGOOGLE_API_KEY=abc\nMAX_TOOL_ROUNDS=3\nDATA_DIR=/x\n",
    )

    settings = Settings(_env_file=env_file)

    assert settings.llm_model == "openai:gpt-4.1-mini"
    assert isinstance(settings.google_api_key, SecretStr)
    assert settings.google_api_key.get_secret_value() == "abc"
    assert "abc" not in repr(settings)
    assert settings.max_tool_rounds == 3
    assert settings.data_dir == Path("/x")


def test_store_today_parsed_as_date(tmp_path: Path) -> None:
    env_file = write_env(tmp_path, "STORE_TODAY=2026-03-23\n")

    assert Settings(_env_file=env_file).store_today == date(2026, 3, 23)


def test_empty_values_are_unset(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    shutil.copy(ENV_EXAMPLE, env_file)

    settings = Settings(_env_file=env_file)

    assert settings.google_api_key is None
    assert settings.store_today is None


def test_export_provider_env_sets_missing(tmp_path: Path) -> None:
    env_file = write_env(tmp_path, "GOOGLE_API_KEY=abc\nLANGSMITH_PROJECT=p\nLLM_MODEL=x:y\n")

    exported = Settings(_env_file=env_file).export_provider_env(env_file)

    assert sorted(exported) == ["GOOGLE_API_KEY", "LANGSMITH_PROJECT"]
    assert os.environ["GOOGLE_API_KEY"] == "abc"
    assert os.environ["LANGSMITH_PROJECT"] == "p"
    assert "LLM_MODEL" not in os.environ


def test_export_provider_env_does_not_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = write_env(tmp_path, "GOOGLE_API_KEY=file\nLANGSMITH_PROJECT=file\n")
    settings = Settings(_env_file=env_file)
    monkeypatch.setenv("GOOGLE_API_KEY", "shell")
    monkeypatch.setenv("LANGSMITH_PROJECT", "shell")

    exported = settings.export_provider_env(env_file)

    assert exported == []
    assert os.environ["GOOGLE_API_KEY"] == "shell"
    assert os.environ["LANGSMITH_PROJECT"] == "shell"


def test_env_example_has_no_real_key() -> None:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    key_lines = [line.lstrip("# ") for line in lines if "_API_KEY=" in line]

    assert key_lines
    assert all(line.split("=", 1)[1] == "" for line in key_lines)
