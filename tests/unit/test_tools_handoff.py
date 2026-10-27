"""request_human_handoff and HandoffLog (design §6.7, FR-13, NFR-02)."""

import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from emporio_musica_support_agent.clock import FixedClock
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.domain import store
from emporio_musica_support_agent.tools.handoff import (
    COMPLAINT_RESPONSE_NOTE,
    HandoffLog,
    HandoffRecord,
    request_human_handoff,
)
from emporio_musica_support_agent.tools.schemas import HandoffInput, HandoffTicket

TZ = ZoneInfo("America/Campo_Grande")
SATURDAY_NOON = datetime(2026, 3, 21, 12, tzinfo=TZ)
SUNDAY_10 = datetime(2026, 3, 22, 10, tzinfo=TZ)
SETTINGS = Settings(_env_file=None)


def handoff(
    log: HandoffLog,
    moment: datetime = SATURDAY_NOON,
    reason: str = "other",
    summary: str = "Cliente quer falar com uma pessoa.",
    order_id: int | None = None,
) -> HandoffTicket:
    params = HandoffInput(reason=reason, summary=summary, order_id=order_id)
    return request_human_handoff(log, FixedClock(moment), SETTINGS, "session-1", params)


def lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def tokens(*values: str) -> Callable[[], str]:
    sequence = iter(values)
    return lambda: next(sequence)


def test_ticket_id_format(tmp_path: Path) -> None:
    ticket = handoff(HandoffLog(tmp_path / "handoffs.jsonl"))

    assert re.fullmatch(r"EMP-\d{8}-[0-9A-F]{4}", ticket.ticket_id)
    assert ticket.ticket_id.startswith("EMP-20260321-")
    assert ticket.created_at == SATURDAY_NOON


def test_log_line_fields_and_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "handoffs.jsonl"
    log = HandoffLog(path)

    ticket = handoff(log, reason="return", order_id=7)
    handoff(log)
    records = lines(path)

    assert len(records) == 2
    assert set(records[0]) == {
        "ticket_id",
        "created_at",
        "session_id",
        "reason",
        "summary",
        "order_id",
    }
    assert records[0]["ticket_id"] == ticket.ticket_id
    assert (records[0]["session_id"], records[0]["order_id"]) == ("session-1", 7)


def test_summary_is_masked_in_the_file(tmp_path: Path) -> None:
    path = tmp_path / "handoffs.jsonl"
    summary = (
        "Cliente leticia.rocha@jmail.com, tel (67) 99789-0123, "
        f"já falou no WhatsApp {store.WHATSAPP}."
    )

    handoff(HandoffLog(path), reason="complaint", summary=summary)
    content = path.read_text(encoding="utf-8")

    assert "leticia.rocha@jmail.com" not in content
    assert "99789-0123" not in content
    assert "le***@jmail.com" in content
    assert "***-0123" in content
    assert store.WHATSAPP in content


def test_complaint_gets_response_time(tmp_path: Path) -> None:
    ticket = handoff(HandoffLog(tmp_path / "h.jsonl"), reason="complaint")

    assert ticket.response_time_note == COMPLAINT_RESPONSE_NOTE


@pytest.mark.parametrize("reason", ["cancellation", "return", "freight_quote", "unknown", "other"])
def test_other_reasons_have_no_response_time(tmp_path: Path, reason: str) -> None:
    ticket = handoff(HandoffLog(tmp_path / "h.jsonl"), reason=reason)

    assert ticket.response_time_note is None


def test_closed_store_says_when_team_is_back(tmp_path: Path) -> None:
    ticket = handoff(HandoffLog(tmp_path / "h.jsonl"), moment=SUNDAY_10)

    assert ticket.team_available_now is False
    assert ticket.next_opening == datetime(2026, 3, 23, 9, tzinfo=TZ)


def test_open_store(tmp_path: Path) -> None:
    ticket = handoff(HandoffLog(tmp_path / "h.jsonl"))

    assert ticket.team_available_now is True
    assert ticket.next_opening is None


def test_ticket_carries_store_contacts(tmp_path: Path) -> None:
    ticket = handoff(HandoffLog(tmp_path / "h.jsonl"))

    assert (ticket.whatsapp, ticket.phone) == (store.WHATSAPP, store.PHONE)
    assert len(ticket.hours) == 3


def taken_log(tmp_path: Path, token: Callable[[], str]) -> HandoffLog:
    log = HandoffLog(tmp_path / "h.jsonl", token=token)
    log.append(
        HandoffRecord(
            ticket_id="EMP-20260321-AAAA",
            created_at=SATURDAY_NOON,
            session_id="earlier",
            reason="other",
            summary="",
            order_id=None,
        )
    )
    return log


def test_ticket_id_retried_on_collision(tmp_path: Path) -> None:
    ticket = handoff(taken_log(tmp_path, tokens("AAAA", "BBBB")))

    assert ticket.ticket_id == "EMP-20260321-BBBB"


def test_ticket_id_gives_up_after_too_many_collisions(tmp_path: Path) -> None:
    log = taken_log(tmp_path, lambda: "AAAA")

    with pytest.raises(RuntimeError, match="no free ticket ID"):
        handoff(log)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"reason": "other", "summary": "x" * 501},
        {"reason": "refund", "summary": "x"},
        {"reason": "other", "summary": "x", "order_id": 0},
    ],
)
def test_invalid_input(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        HandoffInput(**kwargs)
