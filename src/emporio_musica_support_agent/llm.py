"""LLM layer: chat model factory, retry policy and local embeddings (design §4, §14)."""

import logging
import os
from collections.abc import Sequence
from functools import cached_property
from pathlib import Path

from fastembed import TextEmbedding
from langchain.chat_models import init_chat_model
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)
from tenacity.wait import wait_base

from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.logging_setup import log_event

logger = logging.getLogger(__name__)

# init_chat_model provider prefix -> API key variable (None: no key needed).
PROVIDER_API_KEYS: dict[str, str | None] = {
    "google_genai": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama": None,
}
# Providers whose integration package is an optional extra (`uv sync --extra <name>`).
PROVIDER_EXTRAS: dict[str, str] = {"openai": "openai", "anthropic": "anthropic", "ollama": "ollama"}
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
RETRYABLE_NAME_PARTS = ("RateLimit", "ResourceExhausted", "ServiceUnavailable", "Timeout")


class MissingApiKeyError(RuntimeError):
    def __init__(self, variable: str, llm_model: str) -> None:
        self.variable = variable
        super().__init__(f"{variable} is not set; it is required for LLM_MODEL={llm_model}")


class ProviderPackageError(RuntimeError):
    pass


def provider_of(llm_model: str) -> str:
    """The provider prefix of a `provider:model` string, e.g. "google_genai"."""
    provider, separator, _ = llm_model.partition(":")
    if not separator or provider not in PROVIDER_API_KEYS:
        supported = ", ".join(PROVIDER_API_KEYS)
        raise ValueError(f"LLM_MODEL must be '<provider>:<model>' with provider in {supported}")
    return provider


def required_api_key(llm_model: str) -> str | None:
    return PROVIDER_API_KEYS[provider_of(llm_model)]


def check_api_key(settings: Settings) -> None:
    """Raise MissingApiKeyError if the provider's key is in neither settings nor the env."""
    variable = required_api_key(settings.llm_model)
    if variable is None:
        return
    if getattr(settings, variable.lower(), None) is None and not os.environ.get(variable):
        raise MissingApiKeyError(variable, settings.llm_model)


def build_chat_model(settings: Settings) -> BaseChatModel:
    """Provider-agnostic chat model from `LLM_MODEL` (NFR-05)."""
    provider = provider_of(settings.llm_model)
    kwargs: dict[str, object] = {
        "temperature": settings.llm_temperature,
        "timeout": settings.llm_timeout_s,
        "max_retries": 2,  # provider-native transport retries
    }
    if provider == "ollama" and settings.ollama_base_url:
        kwargs["base_url"] = settings.ollama_base_url
    try:
        return init_chat_model(settings.llm_model, **kwargs)  # type: ignore[return-value]
    except ImportError as error:
        extra = PROVIDER_EXTRAS.get(provider)
        hint = f"run `uv sync --extra {extra}`" if extra else "run `uv sync`"
        raise ProviderPackageError(
            f"the integration package for '{provider}' is not installed; {hint}"
        ) from error


def _status_code(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    for value in (
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
        getattr(response, "status_code", None),
    ):
        if isinstance(value, int):
            return value
    return None


def is_retryable(exc: BaseException) -> bool:
    """Rate limits and transient server errors, without importing provider SDKs."""
    if _status_code(exc) in RETRYABLE_STATUS:
        return True
    name = type(exc).__name__
    return any(part in name for part in RETRYABLE_NAME_PARTS)


def _log_retry(state: RetryCallState) -> None:
    error = state.outcome.exception() if state.outcome else None
    log_event(
        logger,
        "llm_retry",
        attempt=state.attempt_number,
        wait_s=round(state.next_action.sleep, 2) if state.next_action else 0,
        error_type=type(error).__name__ if error else None,
        status_code=_status_code(error) if error else None,
    )


def invoke_with_retry(
    model: Runnable[LanguageModelInput, BaseMessage],
    messages: Sequence[BaseMessage],
    settings: Settings,
    wait: wait_base | None = None,
) -> AIMessage:
    """Invoke the model, retrying rate limits and 5xx with exponential backoff (§14)."""
    retrying = Retrying(
        stop=stop_after_attempt(settings.llm_max_retries),
        wait=wait or wait_random_exponential(multiplier=2, max=30),
        retry=retry_if_exception(is_retryable),
        before_sleep=_log_retry,
        reraise=True,
    )
    response = retrying(model.invoke, list(messages))
    if not isinstance(response, AIMessage):
        raise TypeError(f"expected an AIMessage from the model, got {type(response).__name__}")
    return response


class FastEmbedEmbeddings(Embeddings):
    """LangChain `Embeddings` over a local fastembed ONNX model; no API key needed.

    The model loads on first use, so building dependencies or checking the index
    status never triggers the download (~220 MB, cached in `cache_dir`).
    """

    def __init__(self, model_name: str, cache_dir: Path) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir

    @cached_property
    def _model(self) -> TextEmbedding:
        return TextEmbedding(model_name=self.model_name, cache_dir=str(self.cache_dir))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()
