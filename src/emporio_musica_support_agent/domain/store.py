"""Canonical store facts and opening hours (design §6.6, A-03, A-04, A-06).

Times are evaluated in the time zone of the datetime passed in; callers pass
`clock.now(ZoneInfo(settings.store_timezone))`.
"""

from datetime import date, datetime, time, timedelta, tzinfo

STORE_NAME = "Empório da Música"
ADDRESS = "Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, 79202-333"
PHONE = "(67) 3341-4444"
WHATSAPP = "(67) 3321-4500"  # §7; §1.2 lists the phone number for both (D3)
EMAIL = "contato@emporiodamusica.com.br"  # §1.2's accented "empório" is a typo (D3)

# weekday() -> (opens, closes); None = closed. Open means opens <= t < closes.
OPENING_HOURS: dict[int, tuple[time, time] | None] = {
    0: (time(9), time(18)),
    1: (time(9), time(18)),
    2: (time(9), time(18)),
    3: (time(9), time(18)),
    4: (time(9), time(18)),
    5: (time(9), time(13)),
    6: None,
}
HOURS_TABLE: tuple[tuple[str, str], ...] = (
    ("Segunda a Sexta-feira", "09:00 às 18:00"),
    ("Sábado", "09:00 às 13:00"),
    ("Domingo e Feriados", "Fechado"),
)
HOURS_NOTE = (
    "Em datas especiais (Black Friday, Aniversário da Loja, Natal), o horário pode ser "
    "estendido; alterações são avisadas nas redes sociais e no WhatsApp."
)
# No holiday calendar: open_now uses weekday and time only (A-04).
HOLIDAY_NOTE = "Fechado em feriados; não há calendário de feriados no sistema."
SOURCE_SECTIONS: tuple[str, ...] = ("1.2", "2", "7")
WEEKDAYS_PT: tuple[str, ...] = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)
NEXT_OPENING_SCAN_DAYS = 7


def weekday_pt(day: date) -> str:
    return WEEKDAYS_PT[day.weekday()]


def _hours_on(day: date, tz: tzinfo | None) -> tuple[datetime, datetime] | None:
    hours = OPENING_HOURS[day.weekday()]
    if hours is None:
        return None
    opens, closes = hours
    return datetime.combine(day, opens, tzinfo=tz), datetime.combine(day, closes, tzinfo=tz)


def is_open(at: datetime) -> bool:
    hours = _hours_on(at.date(), at.tzinfo)
    return hours is not None and hours[0] <= at < hours[1]


def closes_at(at: datetime) -> datetime | None:
    """Today's closing time while open, else None."""
    hours = _hours_on(at.date(), at.tzinfo)
    return hours[1] if hours is not None and hours[0] <= at < hours[1] else None


def next_opening(at: datetime) -> datetime | None:
    """The next opening after `at` while closed (None while open), scanning up to 7 days."""
    if is_open(at):
        return None
    for offset in range(NEXT_OPENING_SCAN_DAYS + 1):
        hours = _hours_on(at.date() + timedelta(days=offset), at.tzinfo)
        if hours is not None and hours[0] > at:
            return hours[0]
    return None
