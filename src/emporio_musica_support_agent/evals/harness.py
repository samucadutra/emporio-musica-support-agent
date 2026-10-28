"""Run eval cases end to end against the real graph (design §13)."""

import dataclasses
import math
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from emporio_musica_support_agent.agent.graph import build_graph, run_turn
from emporio_musica_support_agent.app import Deps
from emporio_musica_support_agent.clock import FixedClock
from emporio_musica_support_agent.evals.cases import EvalCase, check_expectations
from emporio_musica_support_agent.sessions import (
    new_session_id,
    open_checkpointer,
    session_messages,
)
from emporio_musica_support_agent.tools.handoff import HandoffLog


@dataclass(frozen=True)
class CaseResult:
    id: str
    passed: bool
    failures: list[str]
    tool_calls: list[str]
    latency_ms: list[int]  # one entry per turn
    replies: list[str]
    error: str | None = None  # set when the case could not finish; then `passed` is False


def percentile(values: Sequence[int], q: float) -> int:
    """Nearest-rank percentile (q in 0..100); 0 for no values."""
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


def case_deps(base: Deps, case: EvalCase, workdir: Path) -> Deps:
    """Per-case Deps: the case's date and clock, its own handoff log; data and index shared.

    `store_today` is always the case's value, so a STORE_TODAY in the environment can't leak in.
    """
    return dataclasses.replace(
        base,
        settings=base.settings.model_copy(update={"store_today": case.store_today}),
        clock=FixedClock(case.clock) if case.clock else base.clock,
        handoff_log=HandoffLog(workdir / "handoffs.jsonl"),
    )


def run_case(case: EvalCase, base: Deps, model: BaseChatModel, workdir: Path) -> CaseResult:
    """Send the case's turns on one fresh session and check the expectations."""
    deps = case_deps(base, case, workdir)
    tz = ZoneInfo(deps.settings.store_timezone)
    session_id = new_session_id(deps.clock.now(tz))
    checkpointer = open_checkpointer(workdir / "eval.db")
    replies: list[str] = []
    latency_ms: list[int] = []
    tool_calls: list[str] = []
    try:
        graph = build_graph(deps, checkpointer, model)
        for turn in case.turns:
            started = time.perf_counter()
            replies.append(run_turn(graph, deps.settings, session_id, turn))
            latency_ms.append(round((time.perf_counter() - started) * 1000))
        tool_calls = [
            call["name"]
            for message in session_messages(checkpointer, session_id) or []
            if isinstance(message, AIMessage)
            for call in message.tool_calls
        ]
    except Exception as error:
        return CaseResult(
            case.id,
            False,
            [],
            tool_calls,
            latency_ms,
            replies,
            error=f"{type(error).__name__}: {error}",
        )
    finally:
        checkpointer.conn.close()
    failures = check_expectations(case, tool_calls, replies)
    return CaseResult(case.id, not failures, failures, tool_calls, latency_ms, replies)


def run_cases(
    cases: Sequence[EvalCase],
    base: Deps,
    make_model: Callable[[], BaseChatModel],
    on_result: Callable[[CaseResult], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[CaseResult]:
    """Run every case; an error in one marks it `error` and the rest still run.

    Pauses `eval_delay_s` between cases to respect free-tier rate limits.
    """
    results: list[CaseResult] = []
    for index, case in enumerate(cases):
        if index:
            sleep(base.settings.eval_delay_s)
        with tempfile.TemporaryDirectory(prefix="emporio-eval-") as workdir:
            result = run_case(case, base, make_model(), Path(workdir))
        results.append(result)
        if on_result:
            on_result(result)
    return results
