"""Per-run context passed to the graph and to tools (design §8)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentContext:
    session_id: str
