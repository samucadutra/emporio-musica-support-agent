"""The pure tools wrapped as LangChain tools, with logging (design §6 conventions).

Every wrapper takes a hidden `runtime: ToolRuntime[AgentContext]`: LangChain
injects it and keeps it out of the schema the model sees. It carries the
session ID for logs and for the handoff ticket, which the model never supplies.
"""

import json
import logging
import time
from collections.abc import Callable
from typing import Annotated, Any, Protocol

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, InjectedToolArg, StructuredTool
from pydantic import BaseModel

from emporio_musica_support_agent.agent.context import AgentContext
from emporio_musica_support_agent.app import Deps
from emporio_musica_support_agent.logging_setup import log_event
from emporio_musica_support_agent.privacy import mask_pii
from emporio_musica_support_agent.tools import catalog, handoff, orders, policies, store
from emporio_musica_support_agent.tools.schemas import (
    HandoffInput,
    OrderStatusInput,
    ProductDetailsInput,
    SearchPoliciesInput,
    SearchProductsInput,
)

logger = logging.getLogger(__name__)

TOOL_NAMES: tuple[str, ...] = (
    "search_products",
    "get_product_details",
    "list_categories",
    "get_order_status",
    "search_policies",
    "get_store_info",
    "request_human_handoff",
)


class NoInput(BaseModel):
    """For tools that take no arguments.

    LangChain calls a tool whose schema has no fields with no keyword arguments
    at all, which would drop the injected runtime. This hidden field keeps the
    schema non-empty; the model never sees it.
    """

    runtime: Annotated[Any, InjectedToolArg] = None


class ToolOutput(Protocol):
    def model_dump_json(self, *, exclude_none: bool = ...) -> str: ...
    def summarize(self) -> str: ...


def _make_tool[In: BaseModel](
    name: str,
    pure: Callable[..., Any],
    input_model: type[In],
    call: Callable[[In, AgentContext], ToolOutput],
) -> BaseTool:
    def run(runtime: ToolRuntime[AgentContext], **kwargs: Any) -> tuple[str, dict[str, str]]:
        context = runtime.context
        params = input_model(**kwargs)
        masked_args = mask_pii(json.dumps(kwargs, ensure_ascii=False, default=str))
        started = time.perf_counter()
        try:
            output = call(params, context)
        except Exception as error:
            log_event(
                logger,
                "tool_call",
                session_id=context.session_id,
                tool=name,
                args=masked_args,
                latency_ms=round((time.perf_counter() - started) * 1000),
                ok=False,
                error_type=type(error).__name__,
            )
            raise
        content = output.model_dump_json(exclude_none=True)
        summary = output.summarize()
        log_event(
            logger,
            "tool_call",
            session_id=context.session_id,
            tool=name,
            args=masked_args,
            latency_ms=round((time.perf_counter() - started) * 1000),
            ok=True,
            result_size=len(content),
            summary=summary,
        )
        return content, {"summary": summary}

    return StructuredTool.from_function(
        func=run,
        name=name,
        description=pure.__doc__ or name,
        args_schema=input_model,
        response_format="content_and_artifact",
    )


def build_tools(deps: Deps) -> list[BaseTool]:
    """The 7 agent tools, in TOOL_NAMES order."""
    repo, settings, clock = deps.repo, deps.settings, deps.clock
    return [
        _make_tool(
            "search_products",
            catalog.search_products,
            SearchProductsInput,
            lambda p, _: catalog.search_products(repo, p),
        ),
        _make_tool(
            "get_product_details",
            catalog.get_product_details,
            ProductDetailsInput,
            lambda p, _: catalog.get_product_details(repo, p),
        ),
        _make_tool(
            "list_categories",
            catalog.list_categories,
            NoInput,
            lambda _p, _c: catalog.list_categories(repo),
        ),
        _make_tool(
            "get_order_status",
            orders.get_order_status,
            OrderStatusInput,
            lambda p, _: orders.get_order_status(repo, clock, settings, p),
        ),
        _make_tool(
            "search_policies",
            policies.search_policies,
            SearchPoliciesInput,
            lambda p, _: policies.search_policies(deps.policy_index, p),
        ),
        _make_tool(
            "get_store_info",
            store.get_store_info,
            NoInput,
            lambda _p, _c: store.get_store_info(clock, settings),
        ),
        _make_tool(
            "request_human_handoff",
            handoff.request_human_handoff,
            HandoffInput,
            lambda p, c: handoff.request_human_handoff(
                deps.handoff_log, clock, settings, c.session_id, p
            ),
        ),
    ]
