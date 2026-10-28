"""Test doubles shared across test modules (importable via pytest's `pythonpath`)."""

import hashlib
import math
import uuid
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import Field

from emporio_musica_support_agent.agent.context import AgentContext
from emporio_musica_support_agent.text import fold


def run_tool(tool: BaseTool, args: dict[str, Any], session_id: str = "test-session") -> ToolMessage:
    """Run one tool call inside a minimal graph, so its ToolRuntime is injected."""

    def call(state: MessagesState) -> dict[str, list[AIMessage]]:
        request = {"name": tool.name, "args": args, "id": "call-1"}
        return {"messages": [AIMessage(content="", tool_calls=[request])]}

    builder = StateGraph(MessagesState, context_schema=AgentContext)
    builder.add_node("call", call)
    builder.add_node("tools", ToolNode([tool], handle_tool_errors=True))
    builder.add_edge(START, "call")
    builder.add_edge("call", "tools")
    builder.add_edge("tools", END)
    result = builder.compile().invoke({"messages": []}, context=AgentContext(session_id))
    message = result["messages"][-1]
    assert isinstance(message, ToolMessage)
    return message


class FakeEmbeddings(Embeddings):
    """Deterministic hashed bag of words: texts sharing words get similar vectors.

    No model download. Short words ("de", "a", "em") are skipped so they don't
    dominate the overlap, and 1024 buckets keep word collisions rare.
    """

    dimensions = 1024

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in (w for w in fold(text).split() if len(w) >= 4):
            bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dimensions
            vector[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def tool_call(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """One tool call request with a fresh ID."""
    return {"name": name, "args": args or {}, "id": f"call-{uuid.uuid4().hex[:8]}"}


def calls(*requests: dict[str, Any]) -> AIMessage:
    """An AI message that requests the given tool calls."""
    return AIMessage(content="", tool_calls=list(requests))


class ScriptedChatModel(BaseChatModel):
    """A chat model that replays a script: AI messages, exceptions, or callables.

    The last step repeats when `repeat_last` is set (e.g. an endless tool loop).
    Every message list it receives is recorded in `received`. `bind_tools`
    returns the model itself, so the graph can bind the real tools.
    """

    # Each step: an AIMessage, an Exception to raise, or Callable[[messages], AIMessage].
    script: list[Any] = Field(default_factory=list)
    received: list[list[BaseMessage]] = Field(default_factory=list)
    repeat_last: bool = False

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":  # type: ignore[override]
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.received.append(list(messages))
        if not self.script:
            raise RuntimeError("ScriptedChatModel ran out of steps")
        step = self.script[0] if self.repeat_last and len(self.script) == 1 else self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        message = step(messages) if callable(step) else step
        return ChatResult(generations=[ChatGeneration(message=message)])
