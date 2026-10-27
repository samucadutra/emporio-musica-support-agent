"""Store facts and opening hours (design §6.6, A-04, A-06)."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from emporio_musica_support_agent import privacy
from emporio_musica_support_agent.domain import store
from emporio_musica_support_agent.domain.store import closes_at, is_open, next_opening

TZ = ZoneInfo("America/Campo_Grande")


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """A local time in March 2026: the 21st is a Saturday, the 23rd a Monday."""
    return datetime(2026, 3, day, hour, minute, tzinfo=TZ)


def test_saturday_before_closing() -> None:
    assert is_open(at(21, 12, 59))
    assert closes_at(at(21, 12, 59)) == at(21, 13)
    assert next_opening(at(21, 12, 59)) is None


def test_saturday_at_closing_skips_sunday() -> None:
    assert not is_open(at(21, 13))
    assert closes_at(at(21, 13)) is None
    assert next_opening(at(21, 13)) == at(23, 9)


def test_sunday_closed() -> None:
    assert not is_open(at(22, 10))
    assert next_opening(at(22, 10)) == at(23, 9)


@pytest.mark.parametrize(
    ("moment", "open_", "next_open"),
    [
        (at(25, 8, 59), False, at(25, 9)),  # Wednesday before opening: same day
        (at(25, 9), True, None),
        (at(25, 17, 59), True, None),
        (at(25, 18), False, at(26, 9)),  # after closing: next day
    ],
)
def test_weekday_edges(moment: datetime, open_: bool, next_open: datetime | None) -> None:
    assert is_open(moment) is open_
    assert next_opening(moment) == next_open


def test_weekday_closes_at_six() -> None:
    assert closes_at(at(25, 17, 59)) == at(25, 18)


def test_results_keep_the_time_zone() -> None:
    opening = next_opening(at(22, 10))

    assert opening is not None
    assert opening.tzinfo is TZ


def test_hours_use_the_local_time() -> None:
    utc = datetime(2026, 3, 21, 12, 30, tzinfo=UTC)  # 08:30 in Campo Grande

    assert not is_open(utc.astimezone(TZ))


def test_weekday_pt() -> None:
    assert store.weekday_pt(date(2026, 3, 23)) == "segunda-feira"
    assert store.weekday_pt(date(2026, 3, 21)) == "sábado"


@pytest.mark.parametrize("value", [store.PHONE, store.WHATSAPP, store.EMAIL, store.ADDRESS])
def test_store_contacts_are_never_masked(value: str) -> None:
    assert privacy.mask_pii(value) == value


def test_privacy_store_contacts_match_domain() -> None:
    phones = {"".join(c for c in p if c.isdigit()) for p in (store.PHONE, store.WHATSAPP)}

    assert privacy.STORE_EMAIL == store.EMAIL
    assert phones == privacy.STORE_PHONE_DIGITS
