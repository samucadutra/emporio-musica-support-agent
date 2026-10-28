"""Eval results as a Rich table and a Markdown report (design §13)."""

from collections.abc import Sequence
from datetime import date

from rich.markup import escape
from rich.table import Table

from emporio_musica_support_agent.agent.prompts import PROMPT_VERSION
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.evals.harness import CaseResult, percentile


def status_of(result: CaseResult) -> str:
    if result.error:
        return "ERROR"
    return "PASS" if result.passed else "FAIL"


def summarize_latency(results: Sequence[CaseResult]) -> tuple[int, int]:
    """(p50, p95) per-turn latency in ms over all turns of all cases."""
    turns = [ms for result in results for ms in result.latency_ms]
    return percentile(turns, 50), percentile(turns, 95)


def _problems(result: CaseResult) -> str:
    return result.error or "; ".join(result.failures)


def results_table(results: Sequence[CaseResult]) -> Table:
    table = Table("Case", "Result", "Tools", "Latency (s)", "Problems")
    for result in results:
        colour = {"PASS": "green", "FAIL": "red", "ERROR": "yellow"}[status_of(result)]
        table.add_row(
            result.id,
            f"[{colour}]{status_of(result)}[/{colour}]",
            escape(", ".join(result.tool_calls) or "-"),
            f"{sum(result.latency_ms) / 1000:.1f}",
            escape(_problems(result)),
        )
    return table


def render_report(results: Sequence[CaseResult], settings: Settings, today: date) -> str:
    """Markdown report: totals, then one row per case."""
    passed = sum(1 for r in results if r.passed)
    p50, p95 = summarize_latency(results)
    lines = [
        "# Agent eval report",
        "",
        f"- Date: {today.isoformat()}",
        f"- Model: {settings.llm_model}",
        f"- Prompt version: {PROMPT_VERSION}",
        f"- Pass rate: {passed}/{len(results)}",
        f"- Turn latency: p50 {p50 / 1000:.1f} s · p95 {p95 / 1000:.1f} s",
        "",
        "| Case | Result | Tools | Latency (s) | Problems |",
        "|---|---|---|---|---|",
    ]
    for result in results:
        tools = ", ".join(f"`{name}`" for name in result.tool_calls) or "-"
        problems = _problems(result).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {result.id} | {status_of(result)} | {tools} "
            f"| {sum(result.latency_ms) / 1000:.1f} | {problems} |"
        )
    return "\n".join(lines) + "\n"
