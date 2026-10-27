"""SystemClock and FixedClock."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from emporio_musica_support_agent.clock import Clock, FixedClock, SystemClock

STORE_TZ = ZoneInfo("America/Campo_Grande")


def test_fixed_clock_returns_aware_time_in_requested_zone() -> None:
    clock: Clock = FixedClock(datetime(2026, 2, 20, 10, tzinfo=STORE_TZ))

    now = clock.now(STORE_TZ)

    assert now == datetime(2026, 2, 20, 10, tzinfo=STORE_TZ)
    assert now.tzinfo is not None
    assert now.tzinfo.key == "America/Campo_Grande"


def test_fixed_clock_converts_to_other_zone() -> None:
    clock = FixedClock(datetime(2026, 2, 20, 10, tzinfo=STORE_TZ))

    now = clock.now(ZoneInfo("UTC"))

    assert now.hour == 14
    assert now == clock.at


def test_fixed_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock(datetime(2026, 2, 20, 10))


def test_system_clock_returns_current_aware_time() -> None:
    clock: Clock = SystemClock()

    now = clock.now(STORE_TZ)

    assert now.tzinfo is STORE_TZ
    assert abs(now - datetime.now(UTC)) < timedelta(seconds=5)
