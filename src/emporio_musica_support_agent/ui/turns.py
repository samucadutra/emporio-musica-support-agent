"""Streamlit-free helpers: turn a saved conversation into chat turns with a masked tool trace."""

from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from emporio_musica_support_agent.export import masked_args, tool_result_summary


@dataclass
class Turn:
    question: str
    trace: list[str] = field(default_factory=list)  # same lines as the CLI's --show-tools
    answer: str | None = None


def trace_lines(messages: list[BaseMessage]) -> list[str]:
    """One line per tool call (masked arguments) and one per result summary."""
    lines: list[str] = []
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                lines.append(f"🔧 {call['name']} {masked_args(call['args'])}")
        elif isinstance(message, ToolMessage):
            lines.append(f"→ {tool_result_summary(message)}")
    return lines


def split_turns(messages: list[BaseMessage]) -> list[Turn]:
    """Group saved messages into customer turns; the answer is None until Lia replies."""
    turns: list[Turn] = []
    steps: list[BaseMessage] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            turns.append(Turn(question=message.text))
            steps = []
        elif turns and isinstance(message, AIMessage) and not message.tool_calls:
            turns[-1].trace = trace_lines(steps)
            turns[-1].answer = message.text
        elif turns:
            steps.append(message)
            turns[-1].trace = trace_lines(steps)
    return turns
