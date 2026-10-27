"""Injectable clock, so tests and eval cases can freeze time (design §8)."""

from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Protocol


class Clock(Protocol):
    def now(self, tz: tzinfo) -> datetime:
        """Return the current time as a tz-aware datetime in `tz`."""
        ...


@dataclass(frozen=True)
class SystemClock:
    def now(self, tz: tzinfo) -> datetime:
        return datetime.now(tz)


@dataclass(frozen=True)
class FixedClock:
    at: datetime

    def __post_init__(self) -> None:
        # A naive time would force a guess about its zone.
        if self.at.utcoffset() is None:
            raise ValueError("FixedClock needs a timezone-aware datetime")

    def now(self, tz: tzinfo) -> datetime:
        return self.at.astimezone(tz)
