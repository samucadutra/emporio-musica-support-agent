import dataclasses
from datetime import date
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from emporio_musica_support_agent.app import Deps, build_deps
from emporio_musica_support_agent.clock import FixedClock
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.evals.cases import EvalCase, Expect
from emporio_musica_support_agent.evals.harness import (
    CaseResult,
    case_deps,
    percentile,
    run_cases,
)
from emporio_musica_support_agent.evals.report import (
    render_report,
    results_table,
    summarize_latency,
)
from fakes import FakeEmbeddings, ScriptedChatModel, calls, tool_call


@pytest.fixture
def deps(tmp_settings: Settings) -> Deps:
    return build_deps(tmp_settings, embeddings=FakeEmbeddings())


def case(case_id: str, **kwargs: object) -> EvalCase:
    expect = Expect(**kwargs.pop("expect", {}))  # type: ignore[arg-type]
    return EvalCase(id=case_id, description="d", turns=["oi"], expect=expect, **kwargs)  # type: ignore[arg-type]


def test_percentile_nearest_rank() -> None:
    values = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
    assert percentile(values, 50) == 500
    assert percentile(values, 95) == 1000
    assert percentile([], 50) == 0
    assert percentile([7], 95) == 7


def test_case_deps_applies_case_date_and_clock(deps: Deps, tmp_path: Path) -> None:
    simulated = deps.settings.model_copy(update={"store_today": date(2030, 1, 1)})
    env_deps = dataclasses.replace(deps, settings=simulated)
    one = case("a", store_today=date(2026, 2, 20), clock="2026-02-20T10:00:00-04:00")
    changed = case_deps(env_deps, one, tmp_path)
    assert changed.settings.store_today == date(2026, 2, 20)
    assert isinstance(changed.clock, FixedClock)
    assert changed.repo is deps.repo and changed.policy_index is deps.policy_index
    # no store_today in the case: the environment's value does not leak in
    assert case_deps(env_deps, case("b"), tmp_path).settings.store_today is None


def test_run_cases_pass_fail_error_and_delay(
    deps: Deps, tmp_path: Path, captured_events: object
) -> None:
    scripts = iter(
        [
            [calls(tool_call("list_categories")), AIMessage(content="Vendemos violões.")],
            [AIMessage(content="Não sei.")],
            [RuntimeError("boom")],
        ]
    )
    cases = [
        case("pass", expect={"must_call": ["list_categories"], "must_include": ["violoes"]}),
        case("fail", expect={"must_include": ["violoes"]}),
        case("error"),
    ]
    sleeps: list[float] = []
    seen: list[str] = []
    results = run_cases(
        cases,
        deps,
        lambda: ScriptedChatModel(script=next(scripts)),
        on_result=lambda r: seen.append(r.id),
        sleep=sleeps.append,
    )
    assert [r.passed for r in results] == [True, False, False]
    assert results[0].tool_calls == ["list_categories"]
    assert results[0].replies == ["Vendemos violões."]
    assert len(results[0].latency_ms) == 1
    assert results[1].failures == ["missing 'violoes'"]
    assert results[2].error and "boom" in results[2].error
    assert seen == ["pass", "fail", "error"]
    assert sleeps == [deps.settings.eval_delay_s] * 2


def test_report_contents(deps: Deps) -> None:
    results = [
        CaseResult("a", True, [], ["search_products"], [1000, 3000], ["ok"]),
        CaseResult("b", False, ["missing 'x'"], [], [2000], ["no"]),
        CaseResult("c", False, [], [], [], [], error="RuntimeError: boom"),
    ]
    assert summarize_latency(results) == (2000, 3000)
    text = render_report(results, deps.settings, date(2026, 3, 23))
    for expected in (
        "Pass rate: 1/3",
        "p50 2.0 s · p95 3.0 s",
        deps.settings.llm_model,
        "Prompt version:",
        "2026-03-23",
        "| a | PASS |",
        "| b | FAIL |",
        "| c | ERROR |",
        "missing 'x'",
    ):
        assert expected in text
    assert results_table(results).row_count == 3
