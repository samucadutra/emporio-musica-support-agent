"""The agent: an explicit StateGraph with an agent ⇄ tools loop (design §8)."""

import logging
import time
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime

from emporio_musica_support_agent.agent.context import AgentContext
from emporio_musica_support_agent.agent.prompts import PROMPT_VERSION, build_system_prompt
from emporio_musica_support_agent.app import Deps
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.llm import build_chat_model, invoke_with_retry
from emporio_musica_support_agent.logging_setup import log_event
from emporio_musica_support_agent.tools.registry import build_tools

logger = logging.getLogger(__name__)

FALLBACK_REPLY = (
    "Desculpe, não consegui concluir sua consulta agora. "
    "Posso passar seu atendimento para a nossa equipe?"
)
UNFINISHED_TOOL_CALL = "Not run: the turn stopped after too many tool rounds."

UpdateCallback = Callable[[str, list[BaseMessage]], None]


class AgentState(MessagesState):
    """Messages only; nothing else needs to persist."""


def build_graph(
    deps: Deps, checkpointer: BaseCheckpointSaver, model: BaseChatModel | None = None
) -> CompiledStateGraph:
    """Compile the agent graph. `model` defaults to the configured provider model."""
    tools = build_tools(deps)
    bound = (model or build_chat_model(deps.settings)).bind_tools(tools)

    def agent(state: AgentState, runtime: Runtime[AgentContext]) -> dict[str, list[BaseMessage]]:
        # Prepended on every call and never stored: a resumed session always gets
        # the current prompt version and reference date.
        system = SystemMessage(build_system_prompt(deps.settings, deps.clock))
        started = time.perf_counter()
        response = invoke_with_retry(bound, [system, *state["messages"]], deps.settings)
        usage = response.usage_metadata or {}
        log_event(
            logger,
            "llm_call",
            session_id=runtime.context.session_id if runtime.context else None,
            model=deps.settings.llm_model,
            latency_ms=round((time.perf_counter() - started) * 1000),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            tool_calls_requested=len(response.tool_calls),
        )
        return {"messages": [response]}

    builder = StateGraph(AgentState, context_schema=AgentContext)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer)


def run_config(session_id: str, settings: Settings) -> RunnableConfig:
    """Thread = session; at most `max_tool_rounds` agent ⇄ tools rounds per turn."""
    return {
        "configurable": {"thread_id": session_id},
        "recursion_limit": 2 * settings.max_tool_rounds + 1,
    }


def _close_unfinished_turn(graph: CompiledStateGraph, config: RunnableConfig) -> None:
    """Answer dangling tool calls and save the fallback reply.

    Providers reject a history where an AI tool call has no tool result, so a
    turn cut by the recursion limit must be closed before the next one.
    """
    messages = graph.get_state(config).values.get("messages", [])
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    closing: list[BaseMessage] = [
        ToolMessage(
            content=UNFINISHED_TOOL_CALL,
            tool_call_id=call["id"],
            name=call["name"],
            status="error",
        )
        for m in messages
        if isinstance(m, AIMessage)
        for call in m.tool_calls
        if call["id"] not in answered
    ]
    closing.append(AIMessage(content=FALLBACK_REPLY))
    graph.update_state(config, {"messages": closing}, as_node="agent")


def run_turn(
    graph: CompiledStateGraph,
    settings: Settings,
    session_id: str,
    text: str,
    on_update: UpdateCallback | None = None,
) -> str:
    """Send one customer message and return Lia's reply.

    Streams node updates to `on_update` (the CLI's tool trace). On the recursion
    limit it returns the fixed fallback; any other error is logged and re-raised.
    """
    config = run_config(session_id, settings)
    log_event(logger, "turn_start", session_id=session_id, prompt_version=PROMPT_VERSION)
    started = time.perf_counter()
    tool_calls = llm_calls = 0
    reply = ""
    outcome = "ok"
    try:
        for update in graph.stream(
            {"messages": [HumanMessage(content=text)]},
            config,
            context=AgentContext(session_id),
            stream_mode="updates",
        ):
            for node, values in update.items():
                messages = list((values or {}).get("messages", []))
                if node == "agent":
                    llm_calls += 1
                    for message in messages:
                        if isinstance(message, AIMessage):
                            tool_calls += len(message.tool_calls)
                            if not message.tool_calls:
                                reply = message.text
                if on_update:
                    on_update(node, messages)
    except GraphRecursionError:
        _close_unfinished_turn(graph, config)
        reply, outcome = FALLBACK_REPLY, "recursion_limit"
    except Exception as error:
        outcome = "llm_error"
        log_event(
            logger,
            "turn_end",
            session_id=session_id,
            prompt_version=PROMPT_VERSION,
            latency_ms=round((time.perf_counter() - started) * 1000),
            tool_calls=tool_calls,
            llm_calls=llm_calls,
            outcome=outcome,
            error_type=type(error).__name__,
        )
        raise
    log_event(
        logger,
        "turn_end",
        session_id=session_id,
        prompt_version=PROMPT_VERSION,
        latency_ms=round((time.perf_counter() - started) * 1000),
        tool_calls=tool_calls,
        llm_calls=llm_calls,
        outcome=outcome,
    )
    return reply
