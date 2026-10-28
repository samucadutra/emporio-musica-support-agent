"""Tool registry: LangChain wrappers, logging and summaries (design §6)."""

import json
from collections.abc import Callable

import pytest

from emporio_musica_support_agent.app import Deps, build_deps
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.tools.registry import TOOL_NAMES, NoInput, build_tools
from emporio_musica_support_agent.tools.schemas import (
    HandoffInput,
    OrderStatusInput,
    ProductDetailsInput,
    SearchPoliciesInput,
    SearchProductsInput,
)
from fakes import FakeEmbeddings, run_tool

INPUT_MODELS = {
    "search_products": SearchProductsInput,
    "get_product_details": ProductDetailsInput,
    "list_categories": NoInput,
    "get_order_status": OrderStatusInput,
    "search_policies": SearchPoliciesInput,
    "get_store_info": NoInput,
    "request_human_handoff": HandoffInput,
}


@pytest.fixture
def deps(tmp_settings: Settings) -> Deps:
    deps = build_deps(tmp_settings, embeddings=FakeEmbeddings())
    deps.policy_index.build()
    return deps


@pytest.fixture
def tools(deps: Deps) -> dict:
    return {tool.name: tool for tool in build_tools(deps)}


def test_tool_names_in_order(deps: Deps) -> None:
    assert [tool.name for tool in build_tools(deps)] == list(TOOL_NAMES)


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_schemas_match_input_models(tools: dict, name: str) -> None:
    tool = tools[name]
    model_schema = tool.tool_call_schema.model_json_schema()

    assert tool.args_schema is INPUT_MODELS[name]
    visible_fields = set(INPUT_MODELS[name].model_fields) - {"runtime"}  # NoInput's hidden field
    assert set(model_schema.get("properties", {})) == visible_fields
    assert "runtime" not in model_schema.get("properties", {})
    assert "session_id" not in model_schema.get("properties", {})
    assert tool.description


def test_search_products_returns_json_and_summary(tools: dict) -> None:
    message = run_tool(tools["search_products"], {"category": "violões", "max_price": 1000})
    payload = json.loads(message.content)

    assert len(payload["items"]) == 12
    assert message.artifact == {"summary": "12 results · 83, 85, 89, …"}


def test_handoff_uses_session_from_context(tools: dict, deps: Deps) -> None:
    message = run_tool(
        tools["request_human_handoff"],
        {"reason": "complaint", "summary": "Pedido atrasado."},
        session_id="20260323-1412-a1b2",
    )
    record = json.loads(deps.settings.handoff_log_path.read_text(encoding="utf-8"))

    assert json.loads(message.content)["ticket_id"] == record["ticket_id"]
    assert record["session_id"] == "20260323-1412-a1b2"


def test_tool_call_is_logged_masked(
    tools: dict, captured_events: Callable[[str], list[dict[str, object]]]
) -> None:
    run_tool(
        tools["get_order_status"],
        {"order_id": 7, "email": "leticia.rocha@jmail.com"},
        session_id="s-1",
    )
    fields = captured_events("tool_call")[-1]

    assert fields["tool"] == "get_order_status"
    assert fields["session_id"] == "s-1"
    assert fields["ok"] is True
    assert "le***@jmail.com" in str(fields["args"])
    assert "leticia.rocha@jmail.com" not in str(fields["args"])
    assert str(fields["summary"]).startswith("verified · entregue")


def test_tool_error_becomes_error_message(tools: dict, deps: Deps) -> None:
    for path in deps.policy_index.chroma_dir.iterdir():
        if path.name == "manifest.json":
            path.unlink()

    message = run_tool(tools["search_policies"], {"question": "garantia"})

    assert message.status == "error"


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("search_products", {"query": "saxofone"}),
        ("get_product_details", {"name": "Takamine GD20"}),
        ("get_product_details", {"name": "yamaha"}),
        ("list_categories", {}),
        ("get_order_status", {"order_id": 7, "email": "x@y.com"}),
        ("get_order_status", {"order_id": 7, "email": "leticia.rocha@jmail.com"}),
        ("search_policies", {"question": "garantia"}),
        ("get_store_info", {}),
        ("request_human_handoff", {"reason": "other", "summary": "Quer falar com alguém."}),
    ],
)
def test_summaries_are_one_line(tools: dict, name: str, args: dict) -> None:
    summary = run_tool(tools[name], args).artifact["summary"]

    assert summary
    assert "\n" not in summary
    assert "@" not in summary


def test_deps_fixture_index_is_built(deps: Deps) -> None:
    assert deps.policy_index.status().state == "ok"
