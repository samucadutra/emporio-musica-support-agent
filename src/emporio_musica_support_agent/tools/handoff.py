"""Human handoff tool and its append-only JSONL log (design §6.7)."""

import json
import secrets
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from emporio_musica_support_agent.clock import Clock
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.domain import store
from emporio_musica_support_agent.privacy import mask_pii
from emporio_musica_support_agent.tools.schemas import (
    HandoffInput,
    HandoffReason,
    HandoffTicket,
    OpeningHours,
)

COMPLAINT_RESPONSE_NOTE = "retorno em até 24 horas úteis (seção 7.3)"
MAX_TICKET_ATTEMPTS = 20


class HandoffRecord(BaseModel):
    """One line of the handoff log. The summary is already masked (NFR-02)."""

    ticket_id: str
    created_at: datetime
    session_id: str
    reason: HandoffReason
    summary: str
    order_id: int | None


def random_token() -> str:
    return secrets.token_hex(2).upper()


class HandoffLog:
    def __init__(self, path: Path, token: Callable[[], str] = random_token) -> None:
        self.path = path
        self._token = token

    def ticket_ids(self) -> set[str]:
        if not self.path.is_file():
            return set()
        with self.path.open(encoding="utf-8") as f:
            return {json.loads(line)["ticket_id"] for line in f if line.strip()}

    def new_ticket_id(self, day: date) -> str:
        """`EMP-<YYYYMMDD>-<4 hex>`, retried while it collides with an ID in the file."""
        taken = self.ticket_ids()
        for _ in range(MAX_TICKET_ATTEMPTS):
            ticket_id = f"EMP-{day:%Y%m%d}-{self._token()}"
            if ticket_id not in taken:
                return ticket_id
        raise RuntimeError(f"no free ticket ID after {MAX_TICKET_ATTEMPTS} attempts")

    def append(self, record: HandoffRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")


def request_human_handoff(
    log: HandoffLog, clock: Clock, settings: Settings, session_id: str, params: HandoffInput
) -> HandoffTicket:
    """Pass the case to the store team and get a ticket ID. Call when the customer complains,
    wants to cancel or change an order, wants to start a return or exchange, needs a freight quote
    outside the Campo Grande metro area, asks for a person, or when you can't answer with the
    other tools. Then tell the customer: the ticket ID, that a person from the team will take
    over, the WhatsApp and phone, and the opening hours. If `team_available_now` is false, say
    when the team is back (`next_opening`). For complaints, give `response_time_note`. Never
    promise a cancellation, refund or outcome.
    """
    now = clock.now(ZoneInfo(settings.store_timezone))
    ticket_id = log.new_ticket_id(now.date())
    log.append(
        HandoffRecord(
            ticket_id=ticket_id,
            created_at=now,
            session_id=session_id,
            reason=params.reason,
            # The model is told not to include contacts; mask anyway (NFR-02).
            summary=mask_pii(params.summary),
            order_id=params.order_id,
        )
    )
    return HandoffTicket(
        ticket_id=ticket_id,
        created_at=now,
        reason=params.reason,
        whatsapp=store.WHATSAPP,
        phone=store.PHONE,
        hours=[OpeningHours(days=days, hours=hours) for days, hours in store.HOURS_TABLE],
        team_available_now=store.is_open(now),
        next_opening=store.next_opening(now),
        response_time_note=COMPLAINT_RESPONSE_NOTE if params.reason == "complaint" else None,
    )
