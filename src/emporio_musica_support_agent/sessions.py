"""Session IDs and reading saved conversations from the checkpointer (design §10).

Messages are read straight from the checkpointer, so listing and exporting
sessions needs no model or API key.
"""

import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver

SESSION_ID_RE = re.compile(r"^\d{8}-\d{4}-[0-9a-f]{4}$")


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    updated_at: datetime
    message_count: int


def new_session_id(now: datetime) -> str:
    """Start time plus 4 hex characters, e.g. "20260323-1412-a1b2"."""
    return f"{now:%Y%m%d-%H%M}-{secrets.token_hex(2)}"


def open_checkpointer(path: Path) -> SqliteSaver:
    """A SQLite checkpointer on `path`; the caller closes `saver.conn`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def session_messages(
    checkpointer: BaseCheckpointSaver, session_id: str
) -> list[BaseMessage] | None:
    """The saved messages of a session, or None if it doesn't exist."""
    saved = checkpointer.get_tuple({"configurable": {"thread_id": session_id}})
    if saved is None:
        return None
    return list(saved.checkpoint["channel_values"].get("messages", []))


def recent_exchanges(messages: list[BaseMessage], n: int = 3) -> list[tuple[str, str]]:
    """The last `n` (customer text, Lia reply) pairs; tool steps are skipped."""
    exchanges: list[tuple[str, str]] = []
    question: str | None = None
    for message in messages:
        if isinstance(message, HumanMessage):
            question = message.text
        elif isinstance(message, AIMessage) and not message.tool_calls and question is not None:
            exchanges.append((question, message.text))
            question = None
    return exchanges[-n:]


def list_sessions(checkpointer: BaseCheckpointSaver) -> list[SessionInfo]:
    """Every saved session with its last update and message count, newest first."""
    latest: dict[str, SessionInfo] = {}
    for saved in checkpointer.list(None):
        session_id = saved.config["configurable"]["thread_id"]
        updated_at = datetime.fromisoformat(saved.checkpoint["ts"])
        if session_id in latest and latest[session_id].updated_at >= updated_at:
            continue
        messages = saved.checkpoint["channel_values"].get("messages", [])
        latest[session_id] = SessionInfo(session_id, updated_at, len(messages))
    return sorted(latest.values(), key=lambda s: s.updated_at, reverse=True)
