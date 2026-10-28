"""The agent eval against the real model (marked `llm`; skipped without a key)."""

import time
from pathlib import Path

import pytest

from emporio_musica_support_agent.app import Deps, build_deps
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.evals.cases import EvalCase, load_cases
from emporio_musica_support_agent.evals.harness import run_case
from emporio_musica_support_agent.llm import build_chat_model

CASES = load_cases(Path(__file__).parents[2] / "evals" / "cases.yaml")

pytestmark = [pytest.mark.llm, pytest.mark.embeddings]


@pytest.fixture(scope="module")
def deps() -> Deps:
    settings = Settings()
    settings.export_provider_env()
    deps = build_deps(settings)
    deps.policy_index.build()  # no-op when up to date
    return deps


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_agent_case(case: EvalCase, deps: Deps, tmp_path: Path) -> None:
    time.sleep(deps.settings.eval_delay_s)  # free-tier requests per minute
    result = run_case(case, deps, build_chat_model(deps.settings), tmp_path)
    assert result.error is None, result.error
    details = f"{result.failures}\ntools: {result.tool_calls}\nreplies: {result.replies}"
    assert result.passed, details
