"""Application settings, read from the environment and `.env` (design §3)."""

import os
from datetime import date
from pathlib import Path

from dotenv import dotenv_values
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Variables LangChain provider classes read from os.environ.
PROVIDER_ENV_VARS: tuple[str, ...] = (
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OLLAMA_BASE_URL",
)
LANGSMITH_PREFIX = "LANGSMITH_"


class Settings(BaseSettings):
    # env_ignore_empty: `.env.example` ships `GOOGLE_API_KEY=`; an empty value means unset.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    llm_model: str = "google_genai:gemini-2.5-flash"
    llm_temperature: float = 0.2
    llm_timeout_s: float = 60
    llm_max_retries: int = 4

    google_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    ollama_base_url: str | None = None

    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    data_dir: Path = Path("data")
    var_dir: Path = Path("var")
    chroma_dir: Path = Path("var/chroma")
    models_cache_dir: Path = Path("var/models")
    sqlite_path: Path = Path("var/agent.db")
    handoff_log_path: Path = Path("var/handoffs.jsonl")
    log_level: str = "INFO"
    log_file: Path = Path("var/logs/agent.jsonl")

    store_timezone: str = "America/Campo_Grande"
    store_today: date | None = None

    max_tool_rounds: int = 6
    retrieval_k: int = 4
    eval_delay_s: float = 4

    def export_provider_env(self, env_file: Path | str | None = ".env") -> list[str]:
        """Copy provider keys and `LANGSMITH_*` entries into os.environ.

        pydantic-settings reads `.env` without touching os.environ, but LangChain
        provider classes and LangSmith read their settings from it. Variables that
        are already set are never overwritten. Returns the names that were exported.
        """
        values: dict[str, str] = {}
        for name in PROVIDER_ENV_VARS:
            value = getattr(self, name.lower())
            if isinstance(value, SecretStr):
                value = value.get_secret_value()
            if value:
                values[name] = value

        if env_file is not None and Path(env_file).is_file():
            for name, value in dotenv_values(env_file).items():
                if name.startswith(LANGSMITH_PREFIX) and value:
                    values[name] = value

        exported = [name for name in values if name not in os.environ]
        for name in exported:
            os.environ[name] = values[name]
        return exported
