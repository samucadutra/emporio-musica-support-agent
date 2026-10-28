"""Chat model factory, API key checks and retry policy (design §4, §14)."""

from collections.abc import Callable

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from tenacity import wait_none

from emporio_musica_support_agent import llm
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.llm import (
    MissingApiKeyError,
    ProviderPackageError,
    build_chat_model,
    check_api_key,
    invoke_with_retry,
    is_retryable,
    required_api_key,
)


class HTTPError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class ResourceExhausted(Exception):
    pass


class Response:
    status_code = 502


class WrappedError(Exception):
    response = Response()


class FlakyModel:
    """Fails with the given errors first, then answers."""

    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.calls = 0

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return AIMessage(content="ok")


@pytest.mark.parametrize(
    ("model", "variable"),
    [
        ("google_genai:gemini-2.5-flash", "GOOGLE_API_KEY"),
        ("openai:gpt-4.1-mini", "OPENAI_API_KEY"),
        ("anthropic:claude-haiku-4-5", "ANTHROPIC_API_KEY"),
        ("ollama:qwen3:8b", None),
    ],
)
def test_provider_key_mapping(model: str, variable: str | None) -> None:
    assert required_api_key(model) == variable


@pytest.mark.parametrize("model", ["gemini-2.5-flash", "mistral:large"])
def test_unknown_provider(model: str) -> None:
    with pytest.raises(ValueError, match="LLM_MODEL"):
        required_api_key(model)


def test_missing_key_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(MissingApiKeyError, match="GOOGLE_API_KEY") as excinfo:
        check_api_key(Settings(_env_file=None, google_api_key=None))

    assert excinfo.value.variable == "GOOGLE_API_KEY"


def test_key_found_in_settings_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    check_api_key(Settings(_env_file=None, google_api_key="abc"))

    monkeypatch.setenv("GOOGLE_API_KEY", "from-env")
    check_api_key(Settings(_env_file=None, google_api_key=None))


def test_ollama_needs_no_key() -> None:
    check_api_key(Settings(_env_file=None, llm_model="ollama:qwen3:8b"))


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (HTTPError(429), True),
        (HTTPError(503), True),
        (ResourceExhausted("quota"), True),
        (WrappedError("bad gateway"), True),
        (HTTPError(401), False),
        (ValueError("bad"), False),
    ],
)
def test_is_retryable(error: Exception, retryable: bool) -> None:
    assert is_retryable(error) is retryable


def test_retries_then_succeeds(captured_events: Callable[[str], list[dict[str, object]]]) -> None:
    model = FlakyModel(HTTPError(429), HTTPError(429))

    settings = Settings(_env_file=None)
    reply = invoke_with_retry(model, [HumanMessage("oi")], settings, wait=wait_none())
    retries = captured_events("llm_retry")

    assert reply.content == "ok"
    assert model.calls == 3
    assert [r["attempt"] for r in retries] == [1, 2]
    assert retries[0]["status_code"] == 429


def test_auth_error_is_not_retried() -> None:
    model = FlakyModel(HTTPError(401))

    with pytest.raises(HTTPError):
        invoke_with_retry(model, [HumanMessage("oi")], Settings(_env_file=None), wait=wait_none())
    assert model.calls == 1


def test_gives_up_after_max_retries() -> None:
    model = FlakyModel(*[HTTPError(503)] * 10)
    settings = Settings(_env_file=None, llm_max_retries=3)

    with pytest.raises(HTTPError):
        invoke_with_retry(model, [HumanMessage("oi")], settings, wait=wait_none())
    assert model.calls == 3


def test_missing_provider_package(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_package(*args: object, **kwargs: object) -> None:
        raise ImportError("No module named 'langchain_openai'")

    monkeypatch.setattr(llm, "init_chat_model", no_package)

    with pytest.raises(ProviderPackageError, match="uv sync --extra openai"):
        build_chat_model(Settings(_env_file=None, llm_model="openai:gpt-4.1-mini"))


def test_builds_gemini_model_without_calling_it(monkeypatch: pytest.MonkeyPatch) -> None:
    # Provider classes read their key from the environment (Settings.export_provider_env).
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    model = build_chat_model(Settings(_env_file=None))

    assert type(model).__name__ == "ChatGoogleGenerativeAI"
