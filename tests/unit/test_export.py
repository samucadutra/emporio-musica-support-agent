"""Markdown transcript export (design §11)."""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import InMemorySaver

from emporio_musica_support_agent.agent.graph import build_graph, run_turn
from emporio_musica_support_agent.app import build_deps
from emporio_musica_support_agent.clock import FixedClock
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.export import (
    UnknownSessionError,
    export_session,
    render_transcript,
)
from emporio_musica_support_agent.sessions import session_messages
from fakes import FakeEmbeddings, ScriptedChatModel, calls, tool_call

TZ = ZoneInfo("America/Campo_Grande")
CLOCK = FixedClock(datetime(2026, 10, 27, 15, 2, tzinfo=TZ))
LETICIA_EMAIL = "leticia.rocha@jmail.com"
SESSION = "20260220-1015-a1b2"


@pytest.fixture
def saver(tmp_settings: Settings) -> InMemorySaver:
    """A saved session: a question, a verified order lookup, then the reply."""
    deps = build_deps(tmp_settings, clock=CLOCK, embeddings=FakeEmbeddings())
    saver = InMemorySaver()
    model = ScriptedChatModel(
        script=[
            AIMessage(content="Me passa o número do pedido e o e-mail?"),
            calls(tool_call("get_order_status", {"order_id": 7, "email": LETICIA_EMAIL})),
            AIMessage(content="Seu pedido 7 foi entregue."),
        ]
    )
    graph = build_graph(deps, saver, model)
    run_turn(graph, tmp_settings, SESSION, "Posso devolver meu pedido?")
    run_turn(graph, tmp_settings, SESSION, f"Pedido 7, {LETICIA_EMAIL}")
    return saver


def messages_of(saver: InMemorySaver) -> list[BaseMessage]:
    messages = session_messages(saver, SESSION)
    assert messages is not None
    return messages


def render(saver: InMemorySaver, mask_user: bool = False) -> str:
    return render_transcript(
        messages_of(saver),
        title="Exemplo 4: Devolução",
        model="google_genai:gemini-2.5-flash",
        store_today=date(2026, 2, 20),
        session_id=SESSION,
        exported_at=CLOCK.at,
        mask_user=mask_user,
    )


def test_transcript_layout(saver: InMemorySaver) -> None:
    text = render(saver)

    assert text.startswith("# Exemplo 4: Devolução\n")
    assert "- Model: google_genai:gemini-2.5-flash" in text
    assert "- STORE_TODAY: 2026-02-20" in text
    assert f"- Session: {SESSION} · Exported: 2026-10-27 15:02 (America/Campo_Grande)" in text
    assert "**Cliente:** Posso devolver meu pedido?" in text
    assert "**Lia:** Me passa o número do pedido e o e-mail?" in text
    assert "**Lia:** Seu pedido 7 foi entregue." in text


def test_tool_block_is_masked_and_before_the_reply(saver: InMemorySaver) -> None:
    text = render(saver)
    details = text[text.index("<details>") : text.index("</details>")]

    assert '`get_order_status` {"order_id": 7, "email": "le***@jmail.com"}' in details
    assert "→ verified · entregue" in details
    assert LETICIA_EMAIL not in details
    assert text.index("</details>") < text.index("**Lia:** Seu pedido 7")


def test_customer_text_as_typed_unless_masked(saver: InMemorySaver) -> None:
    assert f"**Cliente:** Pedido 7, {LETICIA_EMAIL}" in render(saver)

    masked = render(saver, mask_user=True)
    assert LETICIA_EMAIL not in masked
    assert "**Cliente:** Pedido 7, le***@jmail.com" in masked


def test_export_session_writes_file(
    saver: InMemorySaver, tmp_settings: Settings, tmp_path: Path
) -> None:
    out = tmp_path / "out" / "exemplo.md"

    path = export_session(saver, tmp_settings, CLOCK, SESSION, out, "Exemplo")
    text = path.read_text(encoding="utf-8")

    assert path == out
    assert text.startswith("# Exemplo\n")
    assert "- STORE_TODAY: not set (real date)" in text


def test_export_default_title_and_path(
    saver: InMemorySaver, tmp_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    path = export_session(saver, tmp_settings, CLOCK, SESSION)

    assert path == Path("examples") / f"{SESSION}.md"
    assert path.read_text(encoding="utf-8").startswith(f"# Sessão {SESSION}\n")


def test_export_unknown_session(saver: InMemorySaver, tmp_settings: Settings) -> None:
    with pytest.raises(UnknownSessionError):
        export_session(saver, tmp_settings, CLOCK, "nope")
