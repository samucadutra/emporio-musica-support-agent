import importlib

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from emporio_musica_support_agent.ui.turns import split_turns, trace_lines
from fakes import tool_call

EMAIL = "leticia.rocha@jmail.com"


def conversation() -> list:
    call = tool_call("get_order_status", {"order_id": 7, "email": EMAIL})
    return [
        HumanMessage(content="Pedido 7?"),
        AIMessage(content="", tool_calls=[call]),
        ToolMessage(
            content="{}", tool_call_id=call["id"], artifact={"summary": "verified · entregue"}
        ),
        AIMessage(content="Entregue!"),
        HumanMessage(content="Obrigado"),
        AIMessage(content="De nada."),
    ]


def test_trace_lines_mask_the_email_and_show_the_summary() -> None:
    lines = trace_lines(conversation()[1:3])
    assert lines[0].startswith("🔧 get_order_status")
    assert "le***@jmail.com" in lines[0] and EMAIL not in lines[0]
    assert lines[1] == "→ verified · entregue"


def test_split_turns_groups_questions_traces_and_answers() -> None:
    first, second = split_turns(conversation())
    assert (first.question, first.answer) == ("Pedido 7?", "Entregue!")
    assert len(first.trace) == 2
    assert (second.question, second.answer, second.trace) == ("Obrigado", "De nada.", [])


def test_split_turns_keeps_an_unanswered_turn() -> None:
    [turn] = split_turns(conversation()[:1])
    assert turn.answer is None


def test_streamlit_app_imports() -> None:
    pytest.importorskip("streamlit")
    module = importlib.import_module("emporio_musica_support_agent.ui.streamlit_app")
    assert callable(module.main)
