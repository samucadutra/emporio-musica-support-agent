"""Command-line interface: the `emporio` console script (design §11).

`make_embeddings` and `make_chat_model` are plain module functions so tests can
swap in fakes; nothing is cached at module level.
"""

import json
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn
from zoneinfo import ZoneInfo

import typer
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from emporio_musica_support_agent.agent.graph import UpdateCallback, build_graph, run_turn
from emporio_musica_support_agent.app import Deps, build_deps, build_policy_index
from emporio_musica_support_agent.clock import SystemClock
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.data.loader import DataFileNotFoundError
from emporio_musica_support_agent.data.validation import DataValidationError, validate
from emporio_musica_support_agent.domain.store import WHATSAPP
from emporio_musica_support_agent.evals.cases import EvalCaseError, load_cases
from emporio_musica_support_agent.evals.harness import CaseResult, run_cases
from emporio_musica_support_agent.evals.report import render_report, results_table, status_of
from emporio_musica_support_agent.export import (
    UnknownSessionError,
    export_session,
    masked_args,
    tool_result_summary,
)
from emporio_musica_support_agent.llm import (
    FastEmbedEmbeddings,
    MissingApiKeyError,
    ProviderPackageError,
    build_chat_model,
    check_api_key,
    is_retryable,
    required_api_key,
)
from emporio_musica_support_agent.logging_setup import configure
from emporio_musica_support_agent.rag.extract import extract_policy
from emporio_musica_support_agent.sessions import (
    list_sessions,
    new_session_id,
    open_checkpointer,
    recent_exchanges,
    session_messages,
)
from emporio_musica_support_agent.tools.orders import reference_date

INSTABILITY_MESSAGE = (
    "Estou com instabilidade para responder agora. Tente de novo em instantes. "
    f"Se preferir, fale com a equipe no WhatsApp {WHATSAPP}."
)
CHAT_HELP = (
    "Comandos: /sair ou /exit (encerrar) · /nova ou /new (nova sessão) · "
    "/exportar [arquivo] ou /export [file] (salvar a conversa) · /ajuda ou /help"
)

app = typer.Typer(
    name="emporio",
    help="Empório da Música customer-support agent (Lia).",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Empório da Música customer-support agent."""


def make_embeddings(settings: Settings) -> Embeddings:
    """The local embedding model; it loads (and downloads once) on first use."""
    return FastEmbedEmbeddings(settings.embedding_model, settings.models_cache_dir)


def make_chat_model(settings: Settings) -> BaseChatModel:
    return build_chat_model(settings)


def _fail(console: Console, message: str, code: int) -> NoReturn:
    console.print(f"[red]Error:[/red] {escape(message)}", soft_wrap=True)  # keep paths copyable
    raise typer.Exit(code=code)


@app.command()
def ingest(
    force: Annotated[
        bool, typer.Option("--force", help="Rebuild even if the index is up to date.")
    ] = False,
) -> None:
    """Build or refresh the policy index; a no-op when nothing changed."""
    console = Console()
    settings = Settings()
    try:
        report = build_policy_index(settings, make_embeddings(settings)).build(force=force)
    except DataFileNotFoundError as error:
        _fail(console, str(error), 1)
    if report.built:
        console.print(f"Indexed {report.chunk_count} policy chunks into {settings.chroma_dir}")
        console.print_json(json.dumps(report.manifest, ensure_ascii=False))
    else:
        console.print(f"Policy index is up to date ({report.chunk_count} chunks).")


def _start_up(console: Console, settings: Settings, verbose: bool) -> Deps:
    """Environment, logging, key check, data, validation and index (design §11, §14)."""
    settings.export_provider_env()
    configure(settings, verbose)
    try:
        check_api_key(settings)
    except MissingApiKeyError as error:
        _fail(console, f"{error}. Set {error.variable} in .env or the environment.", 2)
    except ValueError as error:
        _fail(console, str(error), 2)
    try:
        deps = build_deps(settings, embeddings=make_embeddings(settings))
        validate(deps.repo, extract_policy(deps.policy_index.pdf_path).text)
    except DataFileNotFoundError as error:
        _fail(console, f"{error} (DATA_DIR={settings.data_dir})", 2)
    except DataValidationError as error:
        _fail(console, str(error), 2)
    status = deps.policy_index.status()
    if status.state != "ok":
        reason = status.reason or status.state
        console.print(f"[yellow]Construindo o índice de políticas ({escape(reason)})…[/yellow]")
        try:
            deps.policy_index.build()
        except Exception as error:
            _fail(console, f"could not build the policy index ({error}); run `emporio ingest`", 2)
    return deps


def _header(deps: Deps, session_id: str) -> Panel:
    settings = deps.settings
    today = reference_date(settings, deps.clock)
    simulated = " (simulada)" if settings.store_today else ""
    lines = [
        f"Modelo: {settings.llm_model}",
        f"Data de referência: {today.isoformat()}{simulated}",
        f"Sessão: {session_id}",
        "digite /sair para encerrar · /ajuda para comandos",
    ]
    return Panel("\n".join(lines), title="Empório da Música · Lia", border_style="cyan")


def _tool_trace(console: Console) -> UpdateCallback:
    """Print each tool call (masked arguments) and its one-line result summary."""

    def on_update(node: str, messages: list[BaseMessage]) -> None:
        for message in messages:
            if isinstance(message, AIMessage):
                for call in message.tool_calls:
                    line = f"🔧 {call['name']} {masked_args(call['args'])}"
                    console.print(Text(line, style="dim"))
            elif isinstance(message, ToolMessage):
                console.print(Text(f"   → {tool_result_summary(message)}", style="dim"))

    return on_update


def _print_llm_error(console: Console, error: Exception, settings: Settings, verbose: bool) -> None:
    if is_retryable(error):
        console.print(INSTABILITY_MESSAGE)
        if verbose:
            detail = f"{type(error).__name__}: {error}. Try another LLM_MODEL."
            console.print(Text(detail, style="dim"))
        return
    key = required_api_key(settings.llm_model) or "the provider settings"
    console.print(
        f"[red]Model error:[/red] {escape(str(error))}. Check {key} / LLM_MODEL.", soft_wrap=True
    )


def _chat_loop(
    console: Console,
    graph: CompiledStateGraph,
    deps: Deps,
    checkpointer: BaseCheckpointSaver,
    session_id: str,
    show_tools: bool,
    verbose: bool,
) -> None:
    settings = deps.settings
    tz = ZoneInfo(settings.store_timezone)
    while True:
        try:
            text = console.input("[bold cyan]Você ›[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):  # Ctrl-D, or Ctrl-C at the prompt
            console.print()
            break
        if not text:
            continue
        command, _, argument = text.partition(" ")
        if command in ("/sair", "/exit"):
            break
        if command in ("/nova", "/new"):
            session_id = new_session_id(deps.clock.now(tz))
            console.print(f"Nova sessão: {session_id}")
            continue
        if command in ("/ajuda", "/help"):
            console.print(CHAT_HELP)
            continue
        if command in ("/exportar", "/export"):
            out = Path(argument.strip()) if argument.strip() else None
            try:
                path = export_session(checkpointer, settings, deps.clock, session_id, out)
            except UnknownSessionError:
                console.print("Nada para exportar ainda.")
            else:
                console.print(f"Conversa exportada para {path}")
            continue
        if command.startswith("/"):
            console.print(f"Comando desconhecido: {escape(command)}. {CHAT_HELP}")
            continue

        trace = _tool_trace(console) if show_tools else None
        try:
            with console.status("Lia está digitando…"):
                reply = run_turn(graph, settings, session_id, text, on_update=trace)
        except KeyboardInterrupt:
            console.print("(resposta cancelada)")
            continue
        except Exception as error:
            _print_llm_error(console, error, settings, verbose)
            continue
        console.print(Panel(Markdown(reply), title="Lia", title_align="left", border_style="green"))
    console.print("Até mais! 🎶")


@app.command()
def chat(
    session: Annotated[str | None, typer.Option(help="Resume a saved session.")] = None,
    new: Annotated[bool, typer.Option("--new", help="Start a new session (the default).")] = False,
    show_tools: Annotated[bool, typer.Option(help="Print each tool call.")] = False,
    store_today: Annotated[
        str | None, typer.Option(help="Reference date for order rules (YYYY-MM-DD).")
    ] = None,
    verbose: Annotated[bool, typer.Option(help="Show INFO logs and error details.")] = False,
) -> None:
    """Chat with Lia in the terminal."""
    console = Console()
    if session and new:
        _fail(console, "use either --session or --new, not both", 2)
    settings = Settings()
    if store_today:
        try:
            settings = settings.model_copy(update={"store_today": date.fromisoformat(store_today)})
        except ValueError:
            _fail(console, f"--store-today must be YYYY-MM-DD, got {store_today!r}", 2)
    deps = _start_up(console, settings, verbose)

    checkpointer = open_checkpointer(settings.sqlite_path)
    try:
        try:
            graph = build_graph(deps, checkpointer, make_chat_model(settings))
        except ProviderPackageError as error:
            _fail(console, str(error), 2)
        if session:
            history = session_messages(checkpointer, session)
            if history is None:
                _fail(console, f"unknown session: {session} (see `emporio sessions`)", 1)
            session_id = session
        else:
            history = None
            session_id = new_session_id(deps.clock.now(ZoneInfo(settings.store_timezone)))

        console.print(_header(deps, session_id))
        if history is None:
            console.print(f"Sessão: {session_id} (use --session para continuar)")
        else:
            for question, answer in recent_exchanges(history):
                console.print(Text(f"Você › {question}", style="dim"))
                console.print(Text(f"Lia › {answer}", style="dim"))
        _chat_loop(console, graph, deps, checkpointer, session_id, show_tools, verbose)
    finally:
        checkpointer.conn.close()


@app.command("sessions")
def sessions_command() -> None:
    """List saved chat sessions."""
    console = Console()
    settings = Settings()
    checkpointer = open_checkpointer(settings.sqlite_path)
    try:
        saved = list_sessions(checkpointer)
    finally:
        checkpointer.conn.close()
    if not saved:
        console.print("No saved sessions.")
        return
    tz = ZoneInfo(settings.store_timezone)
    table = Table("Session", "Last update", "Messages")
    for info in saved:
        updated = info.updated_at.astimezone(tz).strftime("%Y-%m-%d %H:%M")
        table.add_row(info.session_id, updated, str(info.message_count))
    console.print(table)


@app.command("export")
def export_command(
    session: Annotated[str, typer.Option(help="Session to export.")],
    out: Annotated[Path | None, typer.Option(help="Default: examples/<session>.md")] = None,
    title: Annotated[str | None, typer.Option(help="Transcript title.")] = None,
    mask_user: Annotated[bool, typer.Option(help="Mask PII in customer text too.")] = False,
) -> None:
    """Write a saved session as a Markdown transcript."""
    console = Console()
    settings = Settings()
    checkpointer = open_checkpointer(settings.sqlite_path)
    try:
        path = export_session(checkpointer, settings, SystemClock(), session, out, title, mask_user)
    except UnknownSessionError:
        _fail(console, f"unknown session: {session} (see `emporio sessions`)", 1)
    finally:
        checkpointer.conn.close()
    console.print(f"Exported to {path}")


@app.command("eval")
def eval_command(
    cases: Annotated[Path, typer.Option(help="Eval cases file.")] = Path("evals/cases.yaml"),
    case: Annotated[
        list[str] | None, typer.Option("--case", help="Run only this case ID (repeatable).")
    ] = None,
    report: Annotated[Path, typer.Option(help="Markdown report path.")] = Path(
        "var/eval-report.md"
    ),
    verbose: Annotated[bool, typer.Option(help="Show INFO logs.")] = False,
) -> None:
    """Run the agent eval cases and write a pass/fail and latency report."""
    console = Console()
    try:
        selected = load_cases(cases)
    except EvalCaseError as error:
        _fail(console, str(error), 2)
    if case:
        unknown = sorted(set(case) - {c.id for c in selected})
        if unknown:
            _fail(console, f"unknown case(s): {', '.join(unknown)}", 2)
        selected = [c for c in selected if c.id in case]
    settings = Settings()
    deps = _start_up(console, settings, verbose)

    def show(result: CaseResult) -> None:
        console.print(f"{status_of(result):5} {result.id}")

    try:
        results = run_cases(selected, deps, lambda: make_chat_model(deps.settings), on_result=show)
    except ProviderPackageError as error:
        _fail(console, str(error), 2)
    console.print(results_table(results))
    report.parent.mkdir(parents=True, exist_ok=True)
    today = reference_date(settings, deps.clock)
    report.write_text(render_report(results, settings, today), encoding="utf-8")
    passed = sum(1 for r in results if r.passed)
    console.print(f"{passed}/{len(results)} passed · report: {report}")
    if passed != len(results):
        raise typer.Exit(code=1)
