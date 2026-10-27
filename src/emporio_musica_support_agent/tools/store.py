"""Store tool: get_store_info (design §6.6)."""

from zoneinfo import ZoneInfo

from emporio_musica_support_agent.clock import Clock
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.domain import store
from emporio_musica_support_agent.tools.schemas import OpeningHours, StoreInfo


def get_store_info(clock: Clock, settings: Settings) -> StoreInfo:
    """Get the store's address, phone, WhatsApp, email, opening hours, and whether it is open
    right now in Campo Grande local time. Use for "where are you", "how do I contact you", "what
    time do you open", "are you open now", and whenever you need the team's contacts or when
    they're back. Use the values exactly as returned. If asked about a holiday, say the store is
    closed on holidays (`holiday_note`).
    """
    # Real clock only, never STORE_TODAY: "open now" is about the present (A-03).
    now = clock.now(ZoneInfo(settings.store_timezone))
    return StoreInfo(
        name=store.STORE_NAME,
        address=store.ADDRESS,
        phone=store.PHONE,
        whatsapp=store.WHATSAPP,
        email=store.EMAIL,
        hours=[OpeningHours(days=days, hours=hours) for days, hours in store.HOURS_TABLE],
        hours_note=store.HOURS_NOTE,
        holiday_note=store.HOLIDAY_NOTE,
        timezone=settings.store_timezone,
        local_datetime=now,
        weekday=store.weekday_pt(now.date()),
        open_now=store.is_open(now),
        next_opening=store.next_opening(now),
        closes_at=store.closes_at(now),
        source_sections=list(store.SOURCE_SECTIONS),
    )
