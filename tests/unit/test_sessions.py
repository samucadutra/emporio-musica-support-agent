"""Session IDs and reading saved sessions (design §10)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage

from emporio_musica_support_agent.agent.graph import build_graph, run_turn
from emporio_musica_support_agent.app import build_deps
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.sessions import (
    SESSION_ID_RE,
    list_sessions,
    new_session_id,
    open_checkpointer,
    recent_exchanges,
    session_messages,
)
from fakes import FakeEmbeddings, ScriptedChatModel


def test_session_id_format() -> None:
    session_id = new_session_id(datetime(2026, 3, 23, 14, 12, tzinfo=ZoneInfo("UTC")))

    assert SESSION_ID_RE.match(session_id)
    assert session_id.startswith("20260323-1412-")


def test_recent_exchanges_skip_tool_steps() -> None:
    messages = [
        HumanMessage("um"),
        AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "c1"}]),
        AIMessage(content="resposta um"),
        HumanMessage("dois"),
        AIMessage(content="resposta dois"),
    ]

    assert recent_exchanges(messages) == [("um", "resposta um"), ("dois", "resposta dois")]
    assert recent_exchanges(messages, n=1) == [("dois", "resposta dois")]


def test_list_and_read_saved_sessions(tmp_settings: Settings) -> None:
    deps = build_deps(tmp_settings, embeddings=FakeEmbeddings())
    checkpointer = open_checkpointer(tmp_settings.sqlite_path)
    try:
        for session_id, reply in (("s-1", "Olá!"), ("s-2", "Oi!")):
            model = ScriptedChatModel(script=[AIMessage(content=reply)])
            run_turn(build_graph(deps, checkpointer, model), tmp_settings, session_id, "Oi")

        saved = {info.session_id: info for info in list_sessions(checkpointer)}
        messages = session_messages(checkpointer, "s-1")
    finally:
        checkpointer.conn.close()

    assert set(saved) == {"s-1", "s-2"}
    assert saved["s-1"].message_count == 2
    assert messages is not None
    assert [m.content for m in messages] == ["Oi", "Olá!"]


def test_unknown_session_is_none(tmp_settings: Settings) -> None:
    checkpointer = open_checkpointer(tmp_settings.sqlite_path)
    try:
        assert session_messages(checkpointer, "nope") is None
        assert list_sessions(checkpointer) == []
    finally:
        checkpointer.conn.close()
