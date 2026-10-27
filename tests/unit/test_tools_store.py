"""get_store_info tool (design §6.6, A-03)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from emporio_musica_support_agent.clock import FixedClock
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.domain import store
from emporio_musica_support_agent.tools.schemas import StoreInfo
from emporio_musica_support_agent.tools.store import get_store_info

TZ = ZoneInfo("America/Campo_Grande")
SATURDAY_12_59 = datetime(2026, 3, 21, 12, 59, tzinfo=TZ)
SUNDAY_10_00 = datetime(2026, 3, 22, 10, tzinfo=TZ)


def info(moment: datetime, store_today: date | None = None) -> StoreInfo:
    return get_store_info(FixedClock(moment), Settings(_env_file=None, store_today=store_today))


def test_open_on_saturday_before_one() -> None:
    result = info(SATURDAY_12_59)

    assert result.open_now
    assert result.closes_at == datetime(2026, 3, 21, 13, tzinfo=TZ)
    assert result.next_opening is None
    assert result.weekday == "sábado"
    assert result.timezone == "America/Campo_Grande"
    assert result.local_datetime.tzinfo is not None
    assert result.local_datetime.utcoffset() == SATURDAY_12_59.utcoffset()


def test_closed_on_sunday() -> None:
    result = info(SUNDAY_10_00)

    assert not result.open_now
    assert result.closes_at is None
    assert result.next_opening == datetime(2026, 3, 23, 9, tzinfo=TZ)


def test_store_facts() -> None:
    result = info(SATURDAY_12_59)

    assert (result.address, result.phone, result.whatsapp, result.email) == (
        store.ADDRESS,
        store.PHONE,
        store.WHATSAPP,
        store.EMAIL,
    )
    assert [(h.days, h.hours) for h in result.hours] == list(store.HOURS_TABLE)
    assert result.holiday_note
    assert result.hours_note
    assert result.source_sections == ["1.2", "2", "7"]


def test_store_today_does_not_change_open_now() -> None:
    real = info(SUNDAY_10_00)
    simulated = info(SUNDAY_10_00, store_today=date(2026, 3, 23))  # a Monday

    assert simulated.open_now == real.open_now
    assert simulated.local_datetime == real.local_datetime
    assert simulated.weekday == "domingo"
