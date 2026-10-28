"""Agent graph wiring with a scripted fake model; no LLM is called (design §8)."""

import json
import sqlite3
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.state import CompiledStateGraph

from emporio_musica_support_agent.agent.graph import (
    FALLBACK_REPLY,
    build_graph,
    run_config,
    run_turn,
)
from emporio_musica_support_agent.app import Deps, build_deps
from emporio_musica_support_agent.config import Settings
from fakes import FakeEmbeddings, ScriptedChatModel, calls, tool_call

SESSION = "20260323-1412-a1b2"


@pytest.fixture
def deps(tmp_settings: Settings) -> Deps:
    return build_deps(tmp_settings, embeddings=FakeEmbeddings())


def state_messages(graph: CompiledStateGraph, settings: Settings) -> list[BaseMessage]:
    return graph.get_state(run_config(SESSION, settings)).values["messages"]


def test_tool_call_then_answer(deps: Deps) -> None:
    model = ScriptedChatModel(
        script=[
            calls(tool_call("search_products", {"category": "violões", "max_price": 1000})),
            AIMessage(content="Temos 12 violões até R$ 1.000,00."),
        ]
    )
    graph = build_graph(deps, InMemorySaver(), model)

    reply = run_turn(graph, deps.settings, SESSION, "Violões até 1000?")
    messages = state_messages(graph, deps.settings)

    assert reply == "Temos 12 violões até R$ 1.000,00."
    assert [type(m).__name__ for m in messages] == [
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
        "AIMessage",
    ]
    tool_message = messages[2]
    assert isinstance(tool_message, ToolMessage)
    assert len(json.loads(tool_message.content)["items"]) == 12
    assert tool_message.artifact["summary"].startswith("12 results")


def test_parallel_tool_calls_all_run(deps: Deps) -> None:
    model = ScriptedChatModel(
        script=[
            calls(tool_call("get_store_info"), tool_call("list_categories")),
            AIMessage(content="Pronto."),
        ]
    )
    graph = build_graph(deps, InMemorySaver(), model)

    run_turn(graph, deps.settings, SESSION, "Onde fica e o que vendem?")
    messages = state_messages(graph, deps.settings)
    tool_names = [m.name for m in messages if isinstance(m, ToolMessage)]

    assert sorted(tool_names) == ["get_store_info", "list_categories"]


def test_tool_error_becomes_message_and_turn_finishes(deps: Deps) -> None:
    # The policy index was never built, so search_policies raises.
    model = ScriptedChatModel(
        script=[
            calls(tool_call("search_policies", {"question": "garantia"})),
            AIMessage(content="Não tenho essa informação agora."),
        ]
    )
    graph = build_graph(deps, InMemorySaver(), model)

    reply = run_turn(graph, deps.settings, SESSION, "Qual a garantia?")
    tool_message = next(
        m for m in state_messages(graph, deps.settings) if isinstance(m, ToolMessage)
    )

    assert tool_message.status == "error"
    assert reply == "Não tenho essa informação agora."


def test_endless_tool_calls_end_in_fallback(deps: Deps) -> None:
    model = ScriptedChatModel(
        script=[lambda _messages: calls(tool_call("get_store_info"))], repeat_last=True
    )
    graph = build_graph(deps, InMemorySaver(), model)

    reply = run_turn(graph, deps.settings, SESSION, "Estão abertos?")
    messages = state_messages(graph, deps.settings)
    requested = {c["id"] for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}

    assert reply == FALLBACK_REPLY
    assert messages[-1].content == FALLBACK_REPLY
    assert requested == answered  # history stays valid for the next turn
    assert len(model.received) <= deps.settings.max_tool_rounds + 1


def test_next_turn_after_fallback_works(deps: Deps) -> None:
    loop = ScriptedChatModel(
        script=[lambda _messages: calls(tool_call("get_store_info"))], repeat_last=True
    )
    saver = InMemorySaver()
    run_turn(build_graph(deps, saver, loop), deps.settings, SESSION, "Estão abertos?")

    answer = ScriptedChatModel(script=[AIMessage(content="Sim!")])
    reply = run_turn(build_graph(deps, saver, answer), deps.settings, SESSION, "E agora?")

    assert reply == "Sim!"


def test_checkpoint_resume_across_graph_instances(deps: Deps, tmp_path: Path) -> None:
    db = tmp_path / "agent.db"
    first_model = ScriptedChatModel(script=[AIMessage(content="Olá! Como posso ajudar?")])
    with sqlite3.connect(db, check_same_thread=False) as connection:
        graph = build_graph(deps, SqliteSaver(connection), first_model)
        run_turn(graph, deps.settings, SESSION, "Oi")

    second_model = ScriptedChatModel(script=[AIMessage(content="Claro.")])
    with sqlite3.connect(db, check_same_thread=False) as connection:
        graph = build_graph(deps, SqliteSaver(connection), second_model)
        run_turn(graph, deps.settings, SESSION, "Pode repetir?")
        history = state_messages(graph, deps.settings)

    seen = second_model.received[0]
    assert any(isinstance(m, HumanMessage) and m.content == "Oi" for m in seen)
    assert [m.content for m in history if isinstance(m, HumanMessage)] == ["Oi", "Pode repetir?"]


def test_system_prompt_sent_but_never_stored(deps: Deps) -> None:
    model = ScriptedChatModel(
        script=[calls(tool_call("get_store_info")), AIMessage(content="Abrimos às 9h.")]
    )
    graph = build_graph(deps, InMemorySaver(), model)

    run_turn(graph, deps.settings, SESSION, "Que horas abrem?")

    assert all(isinstance(received[0], SystemMessage) for received in model.received)
    assert "Lia" in str(model.received[0][0].content)
    assert not any(isinstance(m, SystemMessage) for m in state_messages(graph, deps.settings))


def test_llm_error_is_raised(deps: Deps) -> None:
    model = ScriptedChatModel(script=[ValueError("bad request")])
    graph = build_graph(deps, InMemorySaver(), model)

    with pytest.raises(ValueError, match="bad request"):
        run_turn(graph, deps.settings, SESSION, "Oi")


def test_run_config(deps: Deps) -> None:
    config = run_config(SESSION, deps.settings)

    assert config["configurable"] == {"thread_id": SESSION}
    assert config["recursion_limit"] == 2 * deps.settings.max_tool_rounds + 1
