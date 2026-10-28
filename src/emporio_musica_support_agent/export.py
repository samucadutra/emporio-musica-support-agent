"""Markdown transcripts of saved sessions (design §11).

Tool arguments are always masked. Customer messages are kept as typed (the
data is synthetic) unless `mask_user` is set.
"""

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver

from emporio_musica_support_agent.clock import Clock
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.privacy import mask_pii
from emporio_musica_support_agent.sessions import session_messages

DEFAULT_EXPORT_DIR = Path("examples")


class UnknownSessionError(LookupError):
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"unknown session: {session_id}")


def tool_result_summary(message: ToolMessage) -> str:
    """The one-line summary a tool attached, or "error" for a failed call."""
    if message.status == "error":
        return "error"
    artifact = message.artifact if isinstance(message.artifact, dict) else {}
    return str(artifact.get("summary", "ok"))


def masked_args(args: dict[str, object]) -> str:
    return mask_pii(json.dumps(args, ensure_ascii=False))


def render_transcript(
    messages: list[BaseMessage],
    *,
    title: str,
    model: str,
    store_today: date | None,
    session_id: str,
    exported_at: datetime,
    mask_user: bool = False,
) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Model: {model}",
        f"- STORE_TODAY: {store_today.isoformat() if store_today else 'not set (real date)'}",
        f"- Session: {session_id} · Exported: {exported_at:%Y-%m-%d %H:%M} ({exported_at.tzinfo})",
        "",
    ]
    results = {m.tool_call_id: m for m in messages if isinstance(m, ToolMessage)}
    pending_tools: list[str] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            text = mask_pii(message.text) if mask_user else message.text
            lines += [f"**Cliente:** {text}", ""]
        elif isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                result = results.get(call["id"])
                summary = tool_result_summary(result) if result else "no result"
                pending_tools.append(f"- `{call['name']}` {masked_args(call['args'])} → {summary}")
        elif isinstance(message, AIMessage):
            if pending_tools:
                lines += ["<details><summary>Tools</summary>", "", *pending_tools, "</details>", ""]
                pending_tools = []
            lines += [f"**Lia:** {message.text}", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def export_session(
    checkpointer: BaseCheckpointSaver,
    settings: Settings,
    clock: Clock,
    session_id: str,
    out: Path | None = None,
    title: str | None = None,
    mask_user: bool = False,
) -> Path:
    """Write a session as Markdown. Raises UnknownSessionError."""
    messages = session_messages(checkpointer, session_id)
    if messages is None:
        raise UnknownSessionError(session_id)
    path = out or DEFAULT_EXPORT_DIR / f"{session_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_transcript(
            messages,
            title=title or f"Sessão {session_id}",
            # Sessions don't record their model; this is LLM_MODEL at export time.
            model=settings.llm_model,
            store_today=settings.store_today,
            session_id=session_id,
            exported_at=clock.now(ZoneInfo(settings.store_timezone)),
            mask_user=mask_user,
        ),
        encoding="utf-8",
    )
    return path
