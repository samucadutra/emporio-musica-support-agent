"""CLI commands with fake embeddings and a scripted chat model (no download, no LLM)."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from typer.testing import CliRunner, Result

from emporio_musica_support_agent import cli
from emporio_musica_support_agent.config import Settings
from fakes import FakeEmbeddings, ScriptedChatModel, calls, tool_call

LETICIA_EMAIL = "leticia.rocha@jmail.com"
SESSION_LINE = re.compile(r"Sessão: (\d{8}-\d{4}-[0-9a-f]{4}) \(use --session")

Script = Callable[..., None]


class Throttled(Exception):
    status_code = 429


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, data_dir: Path) -> Path:
    """All generated files under tmp_path; fake embeddings; a key that is never used."""
    var = tmp_path / "var"
    env = {
        "DATA_DIR": str(data_dir),
        "VAR_DIR": str(var),
        "CHROMA_DIR": str(var / "chroma"),
        "MODELS_CACHE_DIR": str(var / "models"),
        "SQLITE_PATH": str(var / "agent.db"),
        "HANDOFF_LOG_PATH": str(var / "handoffs.jsonl"),
        "LOG_FILE": str(var / "logs" / "agent.jsonl"),
        "GOOGLE_API_KEY": "test-key",
        "LLM_MAX_RETRIES": "1",
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    for name in ("STORE_TODAY", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no real .env; default exports land in tmp_path
    monkeypatch.setattr(cli, "make_embeddings", lambda settings: FakeEmbeddings())
    return tmp_path


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch, cli_env: Path) -> Script:
    """Set the replies of the next chat run's model."""

    def set_script(*steps: object) -> None:
        def make(settings: Settings) -> ScriptedChatModel:
            return ScriptedChatModel(script=list(steps))

        monkeypatch.setattr(cli, "make_chat_model", make)

    return set_script


def run(cli_runner: CliRunner, args: list[str], input: str = "") -> Result:
    return cli_runner.invoke(cli.app, args, input=input)


def session_id_from(result: Result) -> str:
    match = SESSION_LINE.search(result.output)
    assert match, result.output
    return match.group(1)


def test_help_lists_commands(cli_runner: CliRunner) -> None:
    result = run(cli_runner, ["--help"])

    assert result.exit_code == 0
    for command in ("chat", "ingest", "sessions", "export"):
        assert command in result.output


def test_ingest_twice_is_up_to_date(cli_runner: CliRunner, cli_env: Path) -> None:
    first = run(cli_runner, ["ingest"])
    second = run(cli_runner, ["ingest"])
    forced = run(cli_runner, ["ingest", "--force"])

    assert first.exit_code == 0, first.output
    assert "Indexed 26 policy chunks" in first.output
    assert "pdf_sha256" in first.output
    assert "up to date (26 chunks)" in second.output
    assert "Indexed 26 policy chunks" in forced.output


def test_ingest_missing_pdf_fails(
    cli_runner: CliRunner, cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(cli_env))

    result = run(cli_runner, ["ingest"])

    assert result.exit_code == 1
    assert "políticas_da_loja.pdf" in result.output


def test_chat_one_exchange(cli_runner: CliRunner, script: Script) -> None:
    script(AIMessage(content="Olá! Como posso ajudar?"))

    result = run(cli_runner, ["chat"], input="Oi\n/sair\n")

    assert result.exit_code == 0, result.output
    assert "Construindo o índice de políticas" in result.output  # first run builds it
    assert "Olá! Como posso ajudar?" in result.output
    session_id_from(result)


def test_chat_resume_shows_previous_turns(cli_runner: CliRunner, script: Script) -> None:
    script(AIMessage(content="Temos ótimos violões!"))
    first = run(cli_runner, ["chat"], input="Quero um violão\n/sair\n")
    session_id = session_id_from(first)

    script()
    resumed = run(cli_runner, ["chat", "--session", session_id], input="/sair\n")

    assert resumed.exit_code == 0, resumed.output
    assert "Quero um violão" in resumed.output
    assert "Temos ótimos violões!" in resumed.output


def test_chat_unknown_session(cli_runner: CliRunner, script: Script) -> None:
    script()

    result = run(cli_runner, ["chat", "--session", "20990101-0000-ffff"], input="/sair\n")

    assert result.exit_code == 1
    assert "unknown session" in result.output


def test_chat_missing_key_exits_2(
    cli_runner: CliRunner, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY")
    script()

    result = run(cli_runner, ["chat"], input="/sair\n")

    assert result.exit_code == 2
    assert "GOOGLE_API_KEY" in result.output


def test_chat_store_today_in_header(cli_runner: CliRunner, script: Script) -> None:
    script()

    result = run(cli_runner, ["chat", "--store-today", "2026-03-23"], input="/sair\n")

    assert "2026-03-23 (simulada)" in result.output


def test_chat_show_tools_masks_arguments(cli_runner: CliRunner, script: Script) -> None:
    script(
        calls(tool_call("get_order_status", {"order_id": 7, "email": LETICIA_EMAIL})),
        AIMessage(content="Seu pedido foi entregue."),
    )

    result = run(cli_runner, ["chat", "--show-tools"], input=f"Pedido 7, {LETICIA_EMAIL}\n/sair\n")

    assert result.exit_code == 0, result.output
    assert "get_order_status" in result.output
    assert "le***@jmail.com" in result.output
    assert "→ verified · entregue" in result.output
    assert LETICIA_EMAIL not in result.output


def test_chat_rate_limit_shows_instability_message(cli_runner: CliRunner, script: Script) -> None:
    script(Throttled("quota"))

    result = run(cli_runner, ["chat"], input="Oi\n/sair\n")

    assert result.exit_code == 0
    assert "instabilidade" in result.output


def test_chat_help_and_new_session(cli_runner: CliRunner, script: Script) -> None:
    script()

    result = run(cli_runner, ["chat"], input="/ajuda\n/nova\n/sair\n")

    assert "/exportar" in result.output
    assert "Nova sessão:" in result.output


def test_chat_export_command(cli_runner: CliRunner, script: Script, cli_env: Path) -> None:
    script(AIMessage(content="Olá!"))

    result = run(cli_runner, ["chat"], input="Oi\n/exportar conversa.md\n/sair\n")

    assert "Conversa exportada" in result.output
    assert "**Lia:** Olá!" in (cli_env / "conversa.md").read_text(encoding="utf-8")


def test_sessions_lists_saved_sessions(cli_runner: CliRunner, script: Script) -> None:
    script(AIMessage(content="Olá!"))
    first = session_id_from(run(cli_runner, ["chat"], input="Oi\n/sair\n"))
    script(AIMessage(content="Oi de novo!"))
    second = session_id_from(run(cli_runner, ["chat"], input="Oi\n/sair\n"))

    result = run(cli_runner, ["sessions"])

    assert result.exit_code == 0
    assert first in result.output
    assert second in result.output


def test_sessions_empty(cli_runner: CliRunner, cli_env: Path) -> None:
    assert "No saved sessions" in run(cli_runner, ["sessions"]).output


def test_export_command(cli_runner: CliRunner, script: Script, cli_env: Path) -> None:
    script(AIMessage(content="Olá!"))
    session_id = session_id_from(run(cli_runner, ["chat"], input="Oi\n/sair\n"))
    out = cli_env / "exemplo.md"

    result = run(
        cli_runner, ["export", "--session", session_id, "--out", str(out), "--title", "Exemplo"]
    )

    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8").startswith("# Exemplo\n")


def test_export_unknown_session(cli_runner: CliRunner, cli_env: Path) -> None:
    result = run(cli_runner, ["export", "--session", "20990101-0000-ffff"])

    assert result.exit_code == 1
    assert "unknown session" in result.output
